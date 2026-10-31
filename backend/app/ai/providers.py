"""AI provider adapters (spec 9.K manual integration boundary).

Implemented: OpenAI-compatible chat APIs, registered as
  AI_PROVIDER=xai  (alias: grok)  -> https://api.x.ai/v1
  AI_PROVIDER=groq                -> https://api.groq.com/openai/v1
  AI_PROVIDER=openai              -> https://api.openai.com/v1
Set AI_BASE_URL to override the endpoint. With no provider configured the app
stays in explicit stub mode (AI_NOT_CONFIGURED).

To add another provider, implement it like this:

    class MyProvider(AIProvider):
        supports_structured = True
        supports_vision = True
        def __init__(self, settings): ...  # read settings.AI_PROVIDER_API_KEY etc.
        def complete_structured(self, system_prompt, user_prompt, images):
            # call the vision-capable LLM with a JSON response format and
            # return the parsed dict / JSON string. Raise ProviderTimeout on
            # timeouts and ProviderError(transient=...) on failures.
            ...

    PROVIDERS["myprovider"] = MyProvider

then set AI_PROVIDER=myprovider, AI_PROVIDER_API_KEY, AI_MODEL_NAME.
"""
from __future__ import annotations

import base64
from typing import Any, Callable

import httpx


class ProviderError(Exception):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class ProviderTimeout(ProviderError):
    def __init__(self, message: str = "timeout"):
        super().__init__(message, transient=True)


class AIProvider:
    supports_structured: bool = False
    supports_vision: bool = False
    supports_transcription: bool = False
    supports_embeddings: bool = False

    def __init__(self, settings: Any):
        self.settings = settings

    def complete_structured(self, system_prompt: str, user_prompt: str, images: list) -> Any:
        raise NotImplementedError  # TODO(manual)

    def transcribe(self, data: bytes, mime_type: str) -> dict:
        raise NotImplementedError  # TODO(manual)

    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError  # TODO(manual)


class OpenAICompatibleProvider(AIProvider):
    """Chat-completions adapter for OpenAI-compatible APIs (xAI Grok, Groq, OpenAI)."""

    supports_structured = True
    supports_vision = True
    # Image formats accepted by these APIs as data URLs.
    VISION_MIME_TYPES = {"image/jpeg", "image/png"}

    def __init__(self, settings: Any, base_url: str, transcription: bool = False, embeddings: bool = False):
        super().__init__(settings)
        self.base_url = (settings.AI_BASE_URL or base_url).rstrip("/")
        self.supports_transcription = transcription
        self.supports_embeddings = embeddings

    def _post(self, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.AI_PROVIDER_API_KEY}"}
        try:
            r = httpx.post(self.base_url + path, headers=headers, timeout=self.settings.AI_TIMEOUT_SECONDS, **kwargs)
        except httpx.TimeoutException:
            raise ProviderTimeout()
        except httpx.HTTPError as exc:
            raise ProviderError(f"connection error: {type(exc).__name__}", transient=True)
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderError(f"HTTP {r.status_code}", transient=True)
        if r.status_code >= 400:
            # Only the provider's short error message is kept (never the request or key).
            detail = ""
            try:
                body = r.json()
                e = body.get("error") if isinstance(body, dict) else None
                detail = (e.get("message") if isinstance(e, dict) else e or body.get("message") or "") if isinstance(body, dict) else ""
            except ValueError:
                pass
            raise ProviderError(f"HTTP {r.status_code} from {self.base_url}: {str(detail)[:200]}")
        try:
            return r.json()
        except ValueError:
            raise ProviderError("non-JSON response")

    def complete_structured(self, system_prompt: str, user_prompt: str, images: list) -> Any:
        content: Any = user_prompt
        usable = [m for m in images if m.mime_type in self.VISION_MIME_TYPES]
        limit = self.settings.AI_MAX_IMAGES
        if limit and limit > 0:
            usable = usable[:limit]
        if usable:
            labels = [f"{m.media_id} (video frame)" if m.media_type == "VIDEO" else m.media_id for m in usable]
            content = [{"type": "text", "text": user_prompt + "\nAttached images (media_id in order): "
                        + ", ".join(labels)}]
            for m in usable:
                b64 = base64.b64encode(m.data).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:{m.mime_type};base64,{b64}"}})
        model = (self.settings.VISION_MODEL_NAME if usable and self.settings.VISION_MODEL_NAME
                 else self.settings.AI_MODEL_NAME)
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        if self.settings.AI_REASONING_EFFORT:
            body["reasoning_effort"] = self.settings.AI_REASONING_EFFORT
        data = self._post("/chat/completions", json=body)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected response shape")

    def transcribe(self, data: bytes, mime_type: str) -> dict:
        ext = mime_type.split("/")[-1].replace("mpeg", "mp3")
        out = self._post("/audio/transcriptions", data={"model": self.settings.SPEECH_MODEL_NAME},
                         files={"file": (f"audio.{ext}", data, mime_type)})
        if not isinstance(out.get("text"), str):
            raise ProviderError("unexpected response shape")
        return {"transcription": out["text"], "language": out.get("language")}

    def embed_text(self, text: str) -> list[float]:
        out = self._post("/embeddings", json={"model": self.settings.EMBEDDING_MODEL_NAME, "input": text})
        try:
            return out["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected response shape")


def _xai(settings: Any) -> AIProvider:
    return OpenAICompatibleProvider(settings, "https://api.x.ai/v1")


def _groq(settings: Any) -> AIProvider:
    return OpenAICompatibleProvider(settings, "https://api.groq.com/openai/v1", transcription=True)


def _openai(settings: Any) -> AIProvider:
    return OpenAICompatibleProvider(settings, "https://api.openai.com/v1", transcription=True, embeddings=True)


# Registry: AI_PROVIDER value (lowercase) -> provider factory.
PROVIDERS: dict[str, Callable[[Any], AIProvider]] = {
    "xai": _xai,
    "grok": _xai,
    "groq": _groq,
    "openai": _openai,
}
