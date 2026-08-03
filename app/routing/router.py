import asyncio
import time
import logging
from collections import defaultdict, deque
from typing import AsyncGenerator, Dict, Optional, Tuple, Type, Any, List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.registry import ModelRegistry
from app.providers import (
    NvidiaProvider,
    BaseProvider,
    ProviderContext,
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    OpenRouterProvider,
)
from app.schemas.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    EmbeddingsRequest,
    EmbeddingsResponse,
)
from app.services.models import ModelRegistryService
from app.core.circuit import circuit_check, circuit_record, CircuitOpenError
from app.core.reqlog import UPSTREAM_ERRORS, set_req
from app.x402.pricing import ROUTE_PRICING

logger = logging.getLogger("cortexcloud.routing.router")

# S3: one persistent provider instance per provider name (they hold the
# shared pooled HTTP clients; recreating per request defeats pooling).
_PROVIDER_INSTANCES: Dict[str, BaseProvider] = {}


class ModelRouter:
    """
    Routing engine responsible for dispatching requests to AI providers.
    Handles retries, latency measurement, and failover/fallback mechanisms.
    """

    PROVIDER_MAP: Dict[str, Type[BaseProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "nvidia": NvidiaProvider,
        "openrouter": OpenRouterProvider,
    }

    # Rolling windows for latency and success/failure per (model_name, provider)
    # Each deque stores tuples (timestamp, value) for latency, and (timestamp, success) for results.
    _latency_window: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=1000))
    _result_window: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=1000))
    _window_duration = 60.0  # seconds

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_provider_api_key(self, provider: str) -> str:
        """Resolve the API key for a provider from global settings."""
        key_map = {
            "openai": settings.OPENAI_API_KEY,
            "anthropic": settings.ANTHROPIC_API_KEY,
            "gemini": settings.GEMINI_API_KEY,
            "groq": settings.GROQ_API_KEY,
            "nvidia": settings.NVIDIA_API_KEY,
            "openrouter": settings.OPENROUTER_API_KEY,
        }

        api_key = key_map.get(provider.lower())
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"API key for provider '{provider}' is not configured on the gateway.",
            )
        return api_key

    def _get_provider(self, provider_name: str) -> BaseProvider:
        """Get the concrete provider instance."""
        provider_class = self.PROVIDER_MAP.get(provider_name.lower())
        if not provider_class:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Provider '{provider_name}' is not supported by the gateway.",
            )
        key = provider_name.lower()
        if key not in _PROVIDER_INSTANCES:
            _PROVIDER_INSTANCES[key] = provider_class()
        return _PROVIDER_INSTANCES[key]

    @staticmethod
    def _has_image_parts(request: ChatCompletionRequest) -> bool:
        """S1: detect vision requests (image_url content parts)."""
        for msg in request.messages:
            content = msg.content
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    @staticmethod
    def _check_vision_support(request: ChatCompletionRequest, model_entry: ModelRegistry) -> None:
        """S1: reject vision requests routed to text-only models with a clear error."""
        if not ModelRouter._has_image_parts(request):
            return
        if not model_entry.capabilities.get("vision", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "vision_unsupported",
                        "message": (
                            f"Model '{model_entry.name}' does not support image inputs. "
                            "Use a vision-capable model (e.g. gemini-2.5-flash, claude-sonnet-4-6)."
                        ),
                        "docs": "https://api.cortexcloud.org/docs",
                    }
                },
            )

    def _update_window(self, model_entry: ModelRegistry, latency_ms: float, success: bool) -> None:
        """Update the sliding window for latency and results."""
        now = time.time()
        latency_sec = latency_ms / 1000.0
        key = (model_entry.name, model_entry.provider)
        
        self._latency_window[key].append((now, latency_sec))
        self._result_window[key].append((now, success))

    def _prune_old_entries(self, dq: deque, current_time: float) -> None:
        """Remove entries older than _window_duration seconds."""
        while dq and (current_time - dq[0][0] > self._window_duration):
            dq.popleft()

    def _get_p95_latency(self, model_name: str, provider: str) -> float:
        """Calculate the 95th percentile latency from the window (last 60 seconds)."""
        key = (model_name, provider)
        latency_deque = self._latency_window[key]
        if not latency_deque:
            return 0.0
        
        now = time.time()
        self._prune_old_entries(latency_deque, now)
        
        if not latency_deque:
            return 0.0
        
        latencies = [val for (_, val) in latency_deque]
        latencies.sort()
        idx = int(0.95 * len(latencies))
        if idx >= len(latencies):
            idx = len(latencies) - 1
        return latencies[idx]

    def _get_error_rate(self, model_name: str, provider: str) -> float:
        """Calculate the error rate from the window (last 60 seconds)."""
        key = (model_name, provider)
        result_deque = self._result_window[key]
        if not result_deque:
            return 0.0
        
        now = time.time()
        self._prune_old_entries(result_deque, now)
        
        if not result_deque:
            return 0.0
        
        successes = sum(1 for (_, success) in result_deque if success)
        total = len(result_deque)
        return 1.0 - (successes / total)

    def _get_cost_for_endpoint(self, endpoint_key: str) -> float:
        """Get the cost in USD for a given endpoint key from ROUTE_PRICING."""
        price_str = ROUTE_PRICING.get(endpoint_key, "$0.00")
        try:
            return float(price_str.lstrip('$'))
        except ValueError:
            return 0.0

    def _score_model_entry(self, model_entry: ModelRegistry, endpoint_key: str) -> float:
        """
        Compute a score for a model-entry (lower is better).
        Score = p95_latency + error_rate + cost
        All components are in comparable units (seconds for latency, ratio for error_rate, dollars for cost).
        """
        p95_latency = self._get_p95_latency(model_entry.name, model_entry.provider)
        error_rate = self._get_error_rate(model_entry.name, model_entry.provider)
        cost = self._get_cost_for_endpoint(endpoint_key)
        return p95_latency + error_rate + cost

    async def _select_best_model(self, model_name: str, endpoint_key: str) -> Optional[ModelRegistry]:
        """
        Select the best model for a given model name based on latency, error rate, and cost.
        Returns the best ModelRegistry entry or None if no active models found.
        """
        all_models = await ModelRegistryService.get_active_models(self.db)
        candidates = [m for m in all_models if m.name == model_name and m.is_active]
        if not candidates:
            return None
        
        # Score each candidate and return the one with the lowest score
        scored = [(self._score_model_entry(m, endpoint_key), m) for m in candidates]
        scored.sort(key=lambda x: x[0])  # sort by score ascending
        return scored[0][1]

    async def route_chat_completion(
        self, request: ChatCompletionRequest, correlation_id: str
    ) -> tuple[ChatCompletionResponse, ModelRegistry, float]:
        """
        Routes chat completion requests with dynamic provider selection based on latency, error rate, and cost.
        Returns: (response, routed_model, latency_ms)
        """
        model_name = request.model
        endpoint_key = "POST /x402/v1/chat/completions"
        
        # Select the best model for this request
        model_entry = await self._select_best_model(model_name, endpoint_key)
        if not model_entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested model '{model_name}' is not registered or active.",
            )
        self._check_vision_support(request, model_entry)

        start_time = time.perf_counter()
        try:
            # 2. Try completing request with retry logic
            response = await self._execute_with_retry(
                self._execute_chat_completion, request, model_entry, correlation_id
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            # Update window with the result of the attempt (success)
            self._update_window(model_entry, latency_ms, True)
            set_req(upstream_provider=model_entry.provider, upstream_latency_ms=latency_ms)
            return response, model_entry, latency_ms
        except HTTPException as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            # Update window with the result of the attempt (failure)
            self._update_window(model_entry, latency_ms, False)
            raise

    async def route_chat_completion_stream(
        self, request: ChatCompletionRequest, correlation_id: str
    ) -> tuple[AsyncGenerator[ChatCompletionStreamResponse, None], ModelRegistry]:
        """
        Routes chat completion streams to the appropriate provider.
        Does not support intermediate buffering retries due to streaming nature,
        but attempts immediate fallback lookup if connection setup fails.
        Note: ponytail: streaming latency and error rates are not tracked (setup-only).
        Add when per-chunk wrapping is needed.
        """
        model_name = request.model
        endpoint_key = "POST /x402/v1/chat/completions"
        
        model_entry = await self._select_best_model(model_name, endpoint_key)
        if not model_entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested model '{model_name}' is not registered or active.",
            )
        self._check_vision_support(request, model_entry)

        try:
            stream = await self._execute_chat_completion_stream(request, model_entry, correlation_id)
            set_req(upstream_provider=model_entry.provider)
            return stream, model_entry
        except HTTPException as primary_err:
            # Immediate failover before streaming starts
            fallback_name = model_entry.capabilities.get("fallback_model")
            if fallback_name and primary_err.status_code in (429, 500, 502, 503, 504):
                logger.info(
                    f"Primary stream '{request.model}' failed with status {primary_err.status_code} "
                    f"on correlation ID {correlation_id}. Initiating fallback to '{fallback_name}'..."
                )
                fallback_entry = await ModelRegistryService.get_model_by_name(self.db, fallback_name)
                if fallback_entry:
                    try:
                        stream = await self._execute_chat_completion_stream(request, fallback_entry, correlation_id)
                        set_req(upstream_provider=fallback_entry.provider)
                        return stream, fallback_entry
                    except Exception as fallback_err:
                        logger.error(
                            f"Fallback stream '{fallback_name}' also failed on correlation ID {correlation_id}: {str(fallback_err)}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Primary stream '{request.model}' failed (HTTP {primary_err.status_code}). Fallback '{fallback_name}' also failed: {str(fallback_err)}",
                        )
            raise primary_err

    async def route_embeddings(
        self, request: EmbeddingsRequest, correlation_id: str
    ) -> tuple[EmbeddingsResponse, ModelRegistry, float]:
        """
        Routes embedding requests.
        Returns:
            Tuple[EmbeddingsResponse, ModelRegistry, float]: (response, routed_model, latency_ms)
        """
        model_name = request.model
        endpoint_key = "POST /x402/v1/embeddings"
        
        model_entry = await self._select_best_model(model_name, endpoint_key)
        if not model_entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested embedding model '{model_name}' is not registered or active.",
            )

        start_time = time.perf_counter()
        try:
            result = await self._execute_with_retry(
                self._execute_embeddings, request, model_entry, correlation_id
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            self._update_window(model_entry, latency_ms, True)
            set_req(upstream_provider=model_entry.provider, upstream_latency_ms=latency_ms)
            return result, model_entry, latency_ms
        except HTTPException as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            self._update_window(model_entry, latency_ms, False)
            raise

    # Execution wrapper functions
    async def _execute_chat_completion(
        self, request: ChatCompletionRequest, model: ModelRegistry, correlation_id: str
    ) -> ChatCompletionResponse:
        provider = self._get_provider(model.provider)
        api_key = self._get_provider_api_key(model.provider)
        
        ctx = ProviderContext(
            api_key=api_key,
            provider_model_name=model.provider_model_name,
            correlation_id=correlation_id,
        )
        # S3: circuit breaker — fail fast with 503 + Retry-After when the
        # provider's error rate exceeds 20% over the last 30s.
        circuit_check(model.provider)
        try:
            result = await provider.chat_completion(request, ctx)
            circuit_record(model.provider, True)
            return result
        except Exception:
            circuit_record(model.provider, False)
            raise

    async def _execute_chat_completion_stream(
        self, request: ChatCompletionRequest, model: ModelRegistry, correlation_id: str
    ) -> AsyncGenerator[ChatCompletionStreamResponse, None]:
        provider = self._get_provider(model.provider)
        api_key = self._get_provider_api_key(model.provider)
        
        ctx = ProviderContext(
            api_key=api_key,
            provider_model_name=model.provider_model_name,
            correlation_id=correlation_id,
        )
        circuit_check(model.provider)
        try:
            stream = provider.chat_completion_stream(request, ctx)
            # ponytail: mid-stream errors aren't recorded (setup-only); a
            # per-chunk wrapper recording errors needs the stream consumer.
            circuit_record(model.provider, True)
            return stream
        except Exception:
            circuit_record(model.provider, False)
            raise

    async def _execute_embeddings(
        self, request: EmbeddingsRequest, model: ModelRegistry, correlation_id: str
    ) -> EmbeddingsResponse:
        provider = self._get_provider(model.provider)
        api_key = self._get_provider_api_key(model.provider)
        
        ctx = ProviderContext(
            api_key=api_key,
            provider_model_name=model.provider_model_name,
            correlation_id=correlation_id,
        )
        circuit_check(model.provider)
        try:
            result = await provider.embeddings(request, ctx)
            circuit_record(model.provider, True)
            return result
        except Exception:
            circuit_record(model.provider, False)
            raise

    # Retry Policy Engine
    async def _execute_with_retry(
        self, func, request, model_entry, correlation_id, max_retries: int = 3, backoff_factor: float = 0.5
    ) -> Any:
        """
        Executes a gateway function with exponential backoff on retryable HTTP errors.
        Returns:
            Any: the result of the function on success.
        Raises:
            HTTPException: on failure after retries.
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                result = await func(request, model_entry, correlation_id)
                return result
            except HTTPException as e:
                last_exception = e
                # S3: never retry an open circuit — fail fast to the caller.
                if isinstance(e, CircuitOpenError):
                    raise e
                UPSTREAM_ERRORS.labels(model_entry.provider).inc()
                # Retry on rate limiting (429) or upstream server issues (5xx)
                if e.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"HTTP {e.status_code} from provider '{model_entry.provider}' for model '{model_entry.name}' "
                            f"on correlation ID {correlation_id}. Retrying attempt {attempt + 1}/{max_retries} in {sleep_time:.2f}s..."
                        )
                        await asyncio.sleep(sleep_time)
                        continue
                raise e
            except Exception as e:
                # Wrap unexpected request network anomalies
                UPSTREAM_ERRORS.labels(model_entry.provider).inc()
                last_exception = HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream provider connection error: {str(e)}",
                )
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Unexpected error from provider '{model_entry.provider}' for model '{model_entry.name}' "
                        f"on correlation ID {correlation_id}: {str(e)}. Retrying attempt {attempt + 1}/{max_retries} in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                raise last_exception

        raise last_exception