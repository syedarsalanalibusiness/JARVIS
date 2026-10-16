import json
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from backend.agent import JarvisAgent
from backend.live import GeminiLiveBridge, friendly_live_error


async def jarvis_socket(websocket: WebSocket, agent: JarvisAgent) -> None:
    await websocket.accept()
    session_id = str(uuid.uuid4())
    mode = {"live_available": False}

    async def send(event: dict) -> None:
        if event.get("type") == "voice_unavailable":
            mode["live_available"] = False
        if event.get("type") == "transcript":
            agent.memory.add(session_id, "user", event.get("text", ""))
        elif event.get("type") == "turn_complete":
            agent.save_answer(session_id, event.get("text", ""))
        await websocket.send_json(event)

    bridge = GeminiLiveBridge(agent.settings, send)
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            kind = message.get("type")
            if kind == "start":
                language = message.get("language", "auto")
                try:
                    await bridge.connect(language)
                    mode["live_available"] = True
                except Exception as exc:
                    start_message = friendly_live_error(exc)
                else:
                    start_message = ""
                await send({
                    "type": "ready",
                    "session_id": session_id,
                    "mode": "voice" if mode["live_available"] else "text",
                    "voice_available": mode["live_available"],
                    "message": start_message,
                })
            elif kind == "audio":
                if mode["live_available"]:
                    try:
                        await bridge.send_audio(message["data"])
                    except Exception as exc:
                        await send({"type": "voice_unavailable", "message": friendly_live_error(exc)})
                else:
                    await send({"type": "chat_error", "message": "Gemini Live voice quota is used up for now. Typed chat is still available; voice can resume when the Live quota resets."})
            elif kind == "audio_end":
                if mode["live_available"]:
                    try:
                        await bridge.end_audio()
                    except Exception as exc:
                        await send({"type": "voice_unavailable", "message": friendly_live_error(exc)})
            elif kind == "text":
                original_text = message.get("text", "").strip()
                if not original_text:
                    await send({"type": "error", "message": "Please enter a question for JARVIS."})
                    continue
                text, sources = await agent.enrich(session_id, original_text)
                if sources:
                    await send({"type": "sources", "items": sources})
                try:
                    answer = await agent.answer_text(
                        text,
                        message.get("language", "auto"),
                        on_local_fallback=lambda: send({
                            "type": "fallback_started",
                            "message": "Gemini is unavailable; trying the local model on this laptop…",
                        }),
                    )
                except Exception as exc:
                    await send({"type": "chat_error", "message": friendly_live_error(exc)})
                    continue
                await send({"type": "response", "text": answer})
                await send({"type": "turn_complete", "text": answer})
            elif kind == "interrupt":
                await bridge.interrupt()
            elif kind == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await send({"type": "error", "message": friendly_live_error(exc)})
    finally:
        if bridge.answer_parts:
            agent.save_answer(session_id, "".join(bridge.answer_parts))
        await bridge.close()
