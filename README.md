# JARVIS — Fast Multilingual Voice AI Web Search Agent

JARVIS is a real-time browser voice assistant built with Python, FastAPI, WebSocket, Gemini Live, SQLite session memory, and a multilingual interface. Browser microphone audio is streamed through the server to Gemini Live; typed chat uses a separate text path.

## Features

- Streaming voice input and output with interruption support
- English, Urdu, Roman Urdu, and automatic multilingual handling
- Separate text chat and voice sessions
- SQLite session memory
- Smart routing for web searches and ordinary questions
- Search sources, calculator, weather, and project-local file tools
- API keys stay server-side; `.env` is excluded by `.gitignore`

## Project layout

- `backend/`: FastAPI app, model routing, Gemini Live bridge, WebSocket, tools, and memory
- `frontend/`: browser interface and microphone/audio client
- `Dockerfile`, `render.yaml`: container and Render Blueprint configuration
- `.env.example`: placeholder environment settings; never put a real key here

## Run locally (Windows)

Requires Python 3.10+ and an optional Gemini API key. Typed chat tries Gemini first and can fall back to local Ollama (`qwen3:4b`); voice uses Gemini Live and requires Gemini access. Quotas and provider availability can affect cloud replies. JARVIS does not enable paid billing automatically.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your own `GEMINI_API_KEY` to the local `.env` if you want Gemini chat and voice. Never commit or share `.env` or put a key in frontend code.

Optional no-API-quota typed-chat fallback: install Ollama, then run `ollama pull qwen3:4b`. It needs a one-time model download and local laptop resources. Public hosting cannot use the Ollama model installed on your laptop.

Start the app:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and allow microphone access. Microphone use requires `localhost` or HTTPS. The `/health` endpoint reports service readiness without returning the API key.

## Public hosting

This repository includes a Render Blueprint (`render.yaml`) and Docker configuration. GitHub stores the source code; it does not run the app or create a public URL by itself. To publish, sign in to a hosting provider, create a service from this repository (or use its Blueprint flow), and set `GEMINI_API_KEY` in the provider's secret/environment settings. Do not commit the secret. Wait for the host build to finish, then open the HTTPS service URL it provides.

The included Render configuration disables Ollama because a cloud service cannot reach the Ollama process on your personal laptop. Gemini chat/voice availability still depends on your Google AI Studio project, model access, network and quota. Confirm the provider's current free-tier limits before presenting this as always-on. A local `127.0.0.1` link is only reachable on the computer running JARVIS.

## Example prompts

- `What is artificial intelligence?`
- `Search for the latest AI news.`
- `Roman Urdu mein explain karo.`
- `458 multiplied by 27`
- `Weather in Lahore`

## Security

- Keep API keys in host secrets or an ignored local `.env` file.
- Never upload `.env`, credentials, personal data, or generated local databases.
- If a real key was exposed, revoke it with its provider and create a replacement.

## Notes

Web search uses DuckDuckGo retrieval by default and weather uses Open-Meteo. For a public production deployment, add authentication, rate limiting, monitoring, and abuse protection.
