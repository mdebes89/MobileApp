"""Thin async clients over the official Mistral HTTP API.

Chat: POST /v1/chat/completions with {model, messages, response_format}.
TTS:  POST /v1/audio/speech with {model, input, voice_id, response_format};
      the response JSON contains base64 audio under `audio_data`.
"""
import base64
import logging
from typing import Any

import httpx

from app.config import get_settings
from app import ratelimit

log = logging.getLogger(__name__)
RATE_LIMIT_KEY = "mistral-api"


class MistralError(RuntimeError):
    pass


async def chat_completion(
    messages: list[dict[str, Any]],
    model: str | None = None,
    json_mode: bool = False,
    timeout: float = 120.0,
) -> str:
    """Call POST /v1/chat/completions and return the assistant message content."""
    settings = get_settings()
    if not ratelimit.check_rate_limit(RATE_LIMIT_KEY, settings.mistral_rpm_limit, settings.mistral_rpm_window):
        raise ratelimit.RateLimitExceeded("Mistral API rate limit exceeded")
    payload: dict[str, Any] = {
        "model": model or settings.mistral_chat_model,
        "messages": messages,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.mistral_base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
        )
    if resp.status_code != 200:
        raise MistralError(f"chat completion failed ({resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise MistralError(f"unexpected chat response shape: {data}") from exc


async def text_to_speech(
    text: str,
    voice_id: str,
    model: str | None = None,
    response_format: str = "wav",
    timeout: float = 300.0,
) -> bytes:
    """Call POST /v1/audio/speech and return decoded audio bytes."""
    settings = get_settings()
    if not ratelimit.check_rate_limit(RATE_LIMIT_KEY, settings.mistral_rpm_limit, settings.mistral_rpm_window):
        raise ratelimit.RateLimitExceeded("Mistral API rate limit exceeded")
    payload = {
        "model": model or settings.mistral_tts_model,
        "input": text,
        "voice_id": voice_id,
        "response_format": response_format,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.mistral_base_url}/audio/speech",
            json=payload,
            headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
        )
    if resp.status_code != 200:
        raise MistralError(f"TTS failed ({resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    audio_b64 = data.get("audio_data") if isinstance(data, dict) else None
    if not audio_b64:
        raise MistralError("TTS response missing audio_data")
    return base64.b64decode(audio_b64)
