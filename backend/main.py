import os
import time
import httpx
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit


def _ignore_unavailable_loopback_proxy() -> None:
    """Avoid sending JARVIS provider requests to a dead local proxy on port 9."""
    proxy_variables = (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    )
    for name in proxy_variables:
        value = os.environ.get(name)
        if not value:
            continue
        try:
            parsed = urlsplit(value if "://" in value else f"http://{value}")
            if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
                os.environ.pop(name, None)
                warnings.warn(
                    f"Ignoring unavailable loopback proxy from {name} for this JARVIS process.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        except ValueError:
            continue


_ignore_unavailable_loopback_proxy()

from fastapi import FastAPI, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.agent import JarvisAgent
from backend.config import get_settings
from backend.memory import MemoryStore
from backend.websocket import jarvis_socket

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
settings = get_settings()
memory = MemoryStore(settings.db_path)
agent = JarvisAgent(settings, memory)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    memory.close()


app = FastAPI(title="JARVIS — Fast Multilingual Voice AI Web Search Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


class TextChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="auto", max_length=30)
    session_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=64)


@app.post("/api/chat")
async def text_chat(request: TextChatRequest):
    question = request.text.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please enter a question for JARVIS.")
    prompt, sources = await agent.enrich(request.session_id, question)
    try:
        answer = await agent.answer_text(prompt, request.language)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    agent.save_answer(request.session_id, answer)
    return {"text": answer, "sources": sources}


_transcription_requests: dict[str, list[float]] = {}


@app.post("/api/transcribe")
async def transcribe_audio(request: Request):
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="Voice backup is not configured yet. Add GROQ_API_KEY to FastAPI Cloud secrets.")
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = [stamp for stamp in _transcription_requests.get(client_ip, []) if now - stamp < 60]
    if len(recent) >= 10:
        raise HTTPException(status_code=429, detail="Too many voice requests. Wait a minute and try again.")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That recording is too large. Keep it under 25 MB.")
    raw_audio = await request.body()
    if not raw_audio:
        raise HTTPException(status_code=400, detail="No audio was received. Hold the mic and try again.")
    if len(raw_audio) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That recording is too large. Keep it under 25 MB.")
    recent.append(now)
    _transcription_requests[client_ip] = recent
    content_type = request.headers.get("content-type", "audio/webm").split(";")[0].strip()
    suffix = {"audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/wav": "wav"}.get(content_type, "webm")
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                data={"model": settings.groq_stt_model, "response_format": "json"},
                files={"file": (f"speech.{suffix}", raw_audio, content_type)},
            )
            response.raise_for_status()
        transcript = response.json().get("text", "").strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech was detected. Try speaking a little longer.")
        return {"text": transcript}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Voice transcription is temporarily unavailable. Try again or type your question.") from exc



@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
async def health():
    return {
        "name": "JARVIS",
        "status": "ready",
        "groq_configured": bool(settings.groq_api_key),
        "text_provider": "Groq free tier" if settings.groq_api_key else None,
        "text_model": settings.groq_text_model if settings.groq_api_key else None,
        "voice_input_provider": "Groq Whisper" if settings.groq_api_key else None,
        "live_voice_enabled": False,
        "local_fallback_enabled": False,
        "local_fallback_model": None,
    }


@app.websocket("/ws/jarvis")
async def websocket_endpoint(websocket: WebSocket):
    await jarvis_socket(websocket, agent)
