import re
import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from google import genai
from google.genai import types

from backend.config import Settings
from backend.memory import MemoryStore
from backend.tools import calculate, search_web
from backend.tools.weather import get_weather

CURRENT_WORDS = ("latest", "current", "today", "news", "search", "google", "web", "recent", "developments", "live", "latest", "aaj", "khabar", "search karo", "google par")
logger = logging.getLogger(__name__)


class JarvisAgent:
    """Routes fast deterministic tools before sending rich context to Gemini Live."""

    def __init__(self, settings: Settings, memory: MemoryStore) -> None:
        self.settings, self.memory = settings, memory

    def needs_search(self, text: str) -> bool:
        return any(word in text.lower() for word in CURRENT_WORDS)

    async def enrich(self, session_id: str, text: str) -> tuple[str, list[dict]]:
        self.memory.add(session_id, "user", text)
        lower = text.lower()
        spoken_math = re.search(r"(\d+(?:\.\d+)?)\s*(?:multiplied by|times|x)\s*(\d+(?:\.\d+)?)", lower)
        if spoken_math:
            result = calculate(f"{spoken_math.group(1)} * {spoken_math.group(2)}")
            return f"The calculator result is: {result}. Explain it briefly in the user's chosen language.", []
        expression = re.fullmatch(
            r"\s*(?:(?:calculate|compute|solve)\s+)?([\d\s+*/().×÷^%-]+)\s*",
            text,
            re.I,
        )
        if expression and any(char.isdigit() for char in expression.group(1)):
            result = calculate(expression.group(1))
            return f"The calculator result is: {result}. Explain it briefly in the user's chosen language.", []
        if "weather" in lower or "mausam" in lower:
            city = re.search(r"(?:weather|mausam)\s+(?:(?:in|of|for|ka|ki)\s+)?([A-Za-z][A-Za-z\s-]*?)(?:\s+(?:today|now|please))?\s*[?.!]*$", text, re.I)
            try:
                weather = await get_weather(city.group(1).strip() if city else self.settings.weather_default_city)
            except Exception as exc:
                weather = {"error": f"Weather lookup failed: {exc}"}
            return f"Current weather data: {weather}. Give a concise helpful answer.", []
        sources = search_web(text, self.settings.search_max_results) if self.needs_search(text) else []
        history = self.memory.context(session_id)
        context = "\n".join(f"{item['role'].title()}: {item['content']}" for item in history[:-1])
        source_text = "\n".join(f"- {s['title']}: {s['snippet']} ({s['url']})" for s in sources)
        prompt = f"Conversation context:\n{context or '(new conversation)'}\n\nUser request: {text}"
        if source_text:
            prompt += f"\n\nFresh web search results (use these, distinguish facts from uncertainty, and mention source names):\n{source_text}"
        return prompt, sources

    def save_answer(self, session_id: str, text: str) -> None:
        self.memory.add(session_id, "assistant", text)

    async def answer_text(
        self,
        prompt: str,
        language: str = "auto",
        on_local_fallback: Callable[[], Awaitable[None]] | None = None,
    ) -> str:
        """Try Gemini first, then a local Ollama model without API quotas."""
        language_instruction = {
            "English": "Answer in English.",
            "Urdu": "جواب اردو میں دیں۔",
            "Roman Urdu": "Roman Urdu mein jawab dein.",
        }.get(language, "Detect the user's language and answer in that language.")
        system_instruction = (
            "You are JARVIS, a friendly multilingual assistant. "
            f"{language_instruction} Be clear and concise, remember the provided conversation context, "
            "and say when you are uncertain. Never claim to have performed an action you did not perform."
        )
        gemini_error: Exception | None = None
        if self.settings.gemini_api_key:
            client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=18_000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=self.settings.gemini_text_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            max_output_tokens=320,
                            temperature=0.5,
                        ),
                    ),
                    timeout=20,
                )
                text = (response.text or "").strip()
                if text:
                    return text
                gemini_error = RuntimeError("Gemini returned an empty response.")
            except asyncio.TimeoutError as exc:
                gemini_error = RuntimeError("Gemini did not answer within 20 seconds.")
                logger.warning("Gemini text response timed out for model %s", self.settings.gemini_text_model)
            except Exception as exc:
                gemini_error = exc
                logger.warning("Gemini failed; trying local fallback model %s", self.settings.ollama_model)
                logger.exception("Gemini text request failed for model %s", self.settings.gemini_text_model)
        else:
            gemini_error = RuntimeError("GEMINI_API_KEY is not configured.")

        if self.settings.ollama_enabled:
            try:
                if on_local_fallback:
                    await on_local_fallback()
                return await self._answer_local(prompt, system_instruction)
            except Exception as local_error:
                logger.warning("Local fallback failed for model %s: %s", self.settings.ollama_model, local_error)
                raise RuntimeError(
                    "Gemini could not answer and the local fallback is not ready. "
                    "Install Ollama, download qwen3:4b, and leave Ollama running; JARVIS will then answer "
                    "locally when the cloud quota or connection fails. No paid billing is enabled automatically."
                ) from (gemini_error or local_error)
        raise RuntimeError(f"Gemini could not answer: {gemini_error}") from gemini_error

    async def _answer_local(self, prompt: str, system_instruction: str) -> str:
        """Use the Ollama loopback API as a no-cloud-quota fallback."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=2.0), trust_env=False) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": 320, "temperature": 0.5},
                },
            )
            response.raise_for_status()
        text = response.json().get("message", {}).get("content", "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response.")
        return text
