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

from fastapi import FastAPI, WebSocket
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
