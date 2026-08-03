"""OpenRouter provider — OpenAI-compatible, used for models not hosted
directly (Mistral, Meta 405B, image gen via Stability/Flux)."""

from app.providers.openai import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    """Routes through OpenRouter's OpenAI-compatible API."""

    def __init__(self, base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(base_url=base_url)
