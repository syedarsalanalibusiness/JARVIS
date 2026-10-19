import os
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

from fastapi import FastAPI, HTTPException, WebSocket
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


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
async def health():
    return {
        "name": "JARVIS",
        "status": "ready",
        "gemini_configured": bool(settings.gemini_api_key),
        "text_model": settings.gemini_text_model,
        "local_fallback_enabled": settings.ollama_enabled,
        "local_fallback_model": settings.ollama_model if settings.ollama_enabled else None,
    }


@app.websocket("/ws/jarvis")
async def websocket_endpoint(websocket: WebSocket):
    await jarvis_socket(websocket, agent)
