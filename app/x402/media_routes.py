"""
x402 payment-gated AI MODALITY endpoints (Wave 2).

Routes to providers whose keys are ACTUALLY configured on CT:
  - Gemini   : images/generations, audio/speech, audio/transcriptions   (GEMINI_API_KEY set)
  - OpenRouter: messages (Anthropic-format passthrough)                 (OPENROUTER_API_KEY set)
  - xAI       : videos/generations (best-effort; 503 if XAI_API_KEY unset)

All gated by the x402 middleware via ROUTE_PRICING. Requests are proxied to the
upstream provider; responses returned as-is (JSON) or streamed bytes (audio).
"""
import base64
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger("cortexcloud.x402.media")

router = APIRouter()

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
XAI_BASE = "https://api.x.ai/v1"


def _need(key: str | None, name: str, prefix: str | None = None, min_len: int = 20):
    """
    Return a 503 response if the provider key is missing or clearly a placeholder.
    Some .env entries store dummy/stub values that are truthy but invalid — guard
    against those so a paying caller gets a clean 'unconfigured' error, not a 403
    from the upstream.
    """
    if not key or len(key) < min_len:
        return JSONResponse(status_code=503, content={"error": "provider_unconfigured", "detail": f"{name} key not configured on gateway"})
    if prefix and not key.startswith(prefix):
        return JSONResponse(status_code=503, content={"error": "provider_unconfigured", "detail": f"{name} key malformed on gateway"})
    return None


# ---------------- Images (Flux/Stability via OpenRouter; Gemini imagen opt-in) ----------------
@router.post("/images/generations")
async def images_generations(body: dict):
    """AI image generation (OpenAI-compatible). Body: {prompt, model?, count?}.

    Default: Flux 1.1 Pro via OpenRouter. Set model to an imagen-* id (or
    provider=\"gemini\") to use Google Imagen instead. Returns provider JSON."""
    prompt = body.get("prompt", "")
    model = body.get("model", "black-forest-labs/flux-1.1-pro")
    count = body.get("count", 1)
    use_gemini = model.startswith("imagen-") or body.get("provider") == "gemini"

    if use_gemini:
        err = _need(settings.GEMINI_API_KEY, "Gemini", prefix="AIza", min_len=30)
        if err:
            return err
        inst = {"prompt": prompt, "aspectRatio": body.get("aspectRatio", "1:1")}
        if "count" in body:
            inst["sampleCount"] = count
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                f"{GEMINI_BASE}/models/{model}:predict",
                params={"key": settings.GEMINI_API_KEY},
                json={"instances": [inst], "parameters": {"storageUri": ""}},
            )
            return JSONResponse(status_code=r.status_code, content=r.json())

    # Default path: OpenRouter (Flux / Stability)
    err = _need(settings.OPENROUTER_API_KEY, "OpenRouter", prefix="sk-or-", min_len=30)
    if err:
        return err
    payload = {"model": model, "prompt": prompt}
    if count and count != 1:
        payload["n"] = count
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{OPENROUTER_BASE}/images/generations",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://cortexcloud.org",
                "X-Title": "CortexCloud",
            },
            json=payload,
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_openrouter", "detail": r.text[:300]})
        return JSONResponse(status_code=200, content=r.json())


@router.post("/images/image2image")
async def images_image2image(body: dict):
    """Image edit via Gemini. Body: {image_b64, prompt, model?}. Returns provider JSON."""
    err = _need(settings.GEMINI_API_KEY, "Gemini", prefix="AIza", min_len=30)
    if err:
        return err
    try:
        img_bytes = base64.b64decode(body["image_b64"])
    except Exception:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": "image_b64 required (base64 PNG)"})
    model = body.get("model", "gemini-2.0-flash-exp-image-generation")
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": body.get("prompt", "Modify this image")},
                {"inline_data": {"mime_type": "image/png", "data": body["image_b64"]}},
            ],
        }]
    }
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{GEMINI_BASE}/models/{model}:generateContent",
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
        )
        return JSONResponse(status_code=r.status_code, content=r.json())


# ---------------- Audio (Gemini TTS / STT) ----------------
@router.post("/audio/speech")
async def audio_speech(body: dict):
    """Gemini text-to-speech. Body: {input, voice?}. Returns WAV audio bytes."""
    err = _need(settings.GEMINI_API_KEY, "Gemini", prefix="AIza", min_len=30)
    if err:
        return err
    voice = body.get("voice", "Kore")
    payload = {
        "contents": [{"parts": [{"text": body.get("input", "")}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{GEMINI_BASE}/models/gemini-2.5-flash-preview-tts:generateContent",
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content=r.json())
        try:
            audio_b64 = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return Response(content=base64.b64decode(audio_b64), media_type="audio/wav")
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": "parse_tts", "detail": str(e)[:200]})


@router.post("/audio/transcriptions")
async def audio_transcriptions(body: dict):
    """Groq Whisper speech-to-text (OpenAI-compatible). Body: {audio_b64, mime?, model?}.
    Returns OpenAI-format transcript JSON: {\"text\": \"...\"}."""
    err = _need(settings.GROQ_API_KEY, "Groq", prefix="gsk_", min_len=30)
    if err:
        return err
    try:
        audio_b64 = body["audio_b64"]
    except Exception:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": "audio_b64 required"})
    mime = body.get("mime", "audio/wav")
    model = body.get("model", "whisper-large-v3-turbo")
    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": "audio_b64 is not valid base64"})
    ext = mime.split("/")[-1].split(";")[0] or "wav"
    files = {"file": (f"audio.{ext}", audio_bytes, mime)}
    data = {"model": model}
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files=files,
            data=data,
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_groq", "detail": r.text[:300]})
        try:
            return JSONResponse({"text": r.json()["text"]})
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": "parse_stt", "detail": str(e)[:200]})


# ---------------- Messages (OpenRouter, Anthropic-format) ----------------
@router.post("/messages")
async def anthropic_messages(request: Request):
    """OpenRouter passthrough accepting Anthropic Messages-format requests."""
    err = _need(settings.OPENROUTER_API_KEY, "OpenRouter", prefix="sk-or-", min_len=30)
    if err:
        return err
    body = await request.json()
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{OPENROUTER_BASE}/messages",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://cortexcloud.org",
                "X-Title": "CortexCloud",
                "content-type": "application/json",
            },
            json=body,
        )
        return JSONResponse(status_code=r.status_code, content=r.json())


# ---------------- Video (xAI Grok, best-effort) ----------------
@router.post("/videos/generations")
async def videos_generations(body: dict):
    """Text-to-video via xAI. Body: {prompt, model?}. 503 if XAI_API_KEY unset."""
    err = _need(settings.XAI_API_KEY, "xAI", prefix="xai-", min_len=20)
    if err:
        return err
    payload = {"model": body.get("model", "grok-video"), "prompt": body.get("prompt", "")}
    for k in ("duration", "aspect_ratio", "resolution"):
        if k in body:
            payload[k] = body[k]
    async with httpx.AsyncClient(timeout=180.0) as c:
        try:
            r = await c.post(
                f"{XAI_BASE}/videos/generations",
                headers={"Authorization": f"Bearer {settings.XAI_API_KEY}"},
                json=payload,
            )
            return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": "upstream_xai", "detail": str(e)[:300]})
