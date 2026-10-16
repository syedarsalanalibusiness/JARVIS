import asyncio
import base64
from typing import Awaitable, Callable

from google import genai
from google.genai import types

from backend.config import Settings

SendEvent = Callable[[dict], Awaitable[None]]


def friendly_live_error(exc: Exception) -> str:
    """Turn provider and OS errors into useful, safe messages for the UI."""
    message = str(exc)
    lowered = message.lower()
    if any(term in lowered for term in ("quota", "resource_exhausted", "429", "rate limit", "too many requests", "1011")):
        return (
            "Gemini's free-tier quota for this model is unavailable or exhausted. "
            "Check Google AI Studio > Usage and wait for the quota to reset. "
            "JARVIS will not enable paid billing automatically."
        )
    if "winerror 5" in lowered or "access is denied" in lowered:
        return (
            "Windows blocked JARVIS from reaching Gemini. Allow outbound HTTPS (port 443) "
            "for this Python environment, then restart JARVIS."
        )
    if any(term in lowered for term in ("winerror 10061", "winerror 1225", "connection refused", "connecterror", "proxyerror")):
        return (
            "JARVIS is running, but this computer cannot reach Google's Gemini API right now "
            "(network or proxy connection refused). Check that internet access is working and "
            "that Windows proxy settings do not point to an unavailable local proxy, then restart JARVIS."
        )
    if "401" in lowered or "403" in lowered or "api key" in lowered:
        return "Gemini rejected the configured API key. Replace GEMINI_API_KEY in .env and restart JARVIS."
    if "404" in lowered or "not found" in lowered:
        return "Gemini could not find the configured Live model. Set GEMINI_LIVE_MODEL to gemini-2.5-flash-native-audio-preview-12-2025 or another Live API model in .env, then restart JARVIS."
    return message


class GeminiLiveBridge:
    """One server-side Gemini Live session. API keys never reach the browser."""

    def __init__(self, settings: Settings, send_event: SendEvent) -> None:
        self.settings, self.send_event = settings, send_event
        self.session = None
        self.receiver: asyncio.Task | None = None
        self.answer_parts: list[str] = []

    async def connect(self, language: str = "auto") -> None:
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env, then restart JARVIS.")
        client = genai.Client(api_key=self.settings.gemini_api_key)
        language_instruction = {
            "English": "Respond in English.",
            "Urdu": "جواب اردو میں دیں۔",
            "Roman Urdu": "Roman Urdu mein jawab dein.",
        }.get(language, "Detect the user's language and answer in that language.")
        config = {
            "response_modalities": ["AUDIO"],
            "input_audio_transcription": {}, "output_audio_transcription": {},
            "tools": [{"google_search": {}}],
            "system_instruction": f"You are JARVIS, a fast, warm multilingual voice AI assistant. {language_instruction} Support English, Urdu, and Roman Urdu. Be concise unless asked for depth. Use supplied web results as the current-information evidence and do not invent citations. Say when information is uncertain. The user can interrupt you at any time.",
        }
        self._context = client.aio.live.connect(model=self.settings.gemini_live_model, config=config)
        self.session = await self._context.__aenter__()
        self.receiver = asyncio.create_task(self._receive())
        await self.send_event({"type": "status", "status": "listening", "language": language})

    async def send_audio(self, audio_b64: str) -> None:
        if self.session:
            await self.session.send_realtime_input(
                audio=types.Blob(data=base64.b64decode(audio_b64), mime_type="audio/pcm;rate=16000")
            )

    async def end_audio(self) -> None:
        if self.session:
            await self.session.send_realtime_input(audio_stream_end=True)

    async def send_text(self, text: str) -> None:
        if self.session:
            self.answer_parts.clear()
            await self.session.send_realtime_input(text=text)

    async def interrupt(self) -> None:
        self.answer_parts.clear()
        if self.session:
            await self.session.send_realtime_input(audio_stream_end=True)
        await self.send_event({"type": "interrupted"})

    async def _receive(self) -> None:
        try:
            async for response in self.session.receive():
                content = getattr(response, "server_content", None)
                if not content:
                    continue
                if getattr(content, "interrupted", False):
                    self.answer_parts.clear()
                    await self.send_event({"type": "interrupted"})
                    continue
                transcription = getattr(content, "input_transcription", None)
                if transcription and transcription.text:
                    await self.send_event({"type": "transcript", "text": transcription.text, "final": True})
                output = getattr(content, "output_transcription", None)
                if output and output.text:
                    self.answer_parts.append(output.text)
                    await self.send_event({"type": "response", "text": output.text})
                turn = getattr(content, "model_turn", None)
                if turn:
                    for part in turn.parts:
                        data = getattr(part, "inline_data", None)
                        if data and data.data:
                            await self.send_event({"type": "audio", "data": base64.b64encode(data.data).decode(), "mime_type": data.mime_type or "audio/pcm;rate=24000"})
                if getattr(content, "turn_complete", False):
                    await self.send_event({"type": "turn_complete", "text": "".join(self.answer_parts)})
        except Exception as exc:
            await self.send_event({"type": "voice_unavailable", "message": friendly_live_error(exc)})

    async def close(self) -> None:
        if self.receiver:
            self.receiver.cancel()
        if self.session:
            await self._context.__aexit__(None, None, None)
