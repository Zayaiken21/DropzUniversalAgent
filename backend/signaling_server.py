# signaling_server.py

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chat_backend.chat_db import add_message


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_DIR = Path("chat_backend/uploads")
VOICE_DIR = UPLOAD_DIR / "voice_notes"

VOICE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Conn:
    websocket: WebSocket
    user_name: str
    user_id: str
    room_id: str


rooms: Dict[str, Dict[str, Conn]] = {}


async def _safe_send(conn: Conn, payload_text: str):
    try:
        await conn.websocket.send_text(payload_text)
        return True
    except Exception:
        return False


async def send_to_user(room_id: str, target_id: str, payload: dict):
    room = rooms.get(room_id, {})
    conn = room.get(target_id)

    if not conn:
        return False

    ok = await _safe_send(conn, json.dumps(payload))

    if not ok:
        room.pop(target_id, None)

    return ok


async def broadcast(room_id: str, payload: dict, exclude_user_id: Optional[str] = None):
    payload_text = json.dumps(payload)
    room = rooms.get(room_id, {})
    dead = []

    for uid, conn in list(room.items()):
        if exclude_user_id and uid == exclude_user_id:
            continue

        ok = await _safe_send(conn, payload_text)

        if not ok:
            dead.append(uid)

    for uid in dead:
        room.pop(uid, None)


async def broadcast_presence(room_id: str):
    room = rooms.get(room_id, {})

    users = [
        {
            "user_id": conn.user_id,
            "user_name": conn.user_name,
            "room_id": conn.room_id,
            "online": True,
        }
        for conn in room.values()
    ]

    await broadcast(
        room_id,
        {
            "type": "presence_snapshot",
            "room_id": room_id,
            "users": users,
            "online_count": len(users),
        }
    )


@app.post("/upload_voice_note")
async def upload_voice_note(
    file: UploadFile = File(...),
    room_id: str = Form("main"),
    user_id: str = Form("guest"),
    user_name: str = Form("Guest"),
    role: str = Form("client"),
):
    suffix = Path(file.filename or "voice_note.webm").suffix or ".webm"
    safe_name = f"voice_{uuid.uuid4().hex}{suffix}"
    file_path = VOICE_DIR / safe_name

    data = await file.read()

    with open(file_path, "wb") as f:
        f.write(data)

    media_path = str(file_path).replace("\\", "/")
    media_type = file.content_type or "audio/webm"

    add_message(
        user_name=user_name,
        role=role,
        message="🎙️ Voice note",
        media_path=media_path,
        media_type=media_type,
        room_id=room_id,
    )

    payload = {
        "type": "chat_message",
        "room_id": room_id,
        "user_id": user_id,
        "user_name": user_name,
        "role": role,
        "message": "🎙️ Voice note",
        "media_path": media_path,
        "media_type": media_type,
        "created_at": None,
    }

    await broadcast(room_id, payload)

    return JSONResponse(
        {
            "ok": True,
            "media_path": media_path,
            "media_type": media_type,
        }
    )


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()

    user_name = "Guest"
    user_id = str(id(websocket))
    room_id = "main"

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except Exception:
                continue

            msg_type = msg.get("type", "")

            user_name = msg.get("user_name", user_name)
            user_id = str(msg.get("user_id", user_id))
            room_id = msg.get("room_id", room_id)

            rooms.setdefault(room_id, {})[user_id] = Conn(
                websocket=websocket,
                user_name=user_name,
                user_id=user_id,
                room_id=room_id,
            )

            target_id = msg.get("target_id")

            if msg_type == "join":
                await broadcast_presence(room_id)

            elif msg_type == "chat_message":
                await broadcast(
                    room_id,
                    {
                        "type": "chat_message",
                        "room_id": room_id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "role": msg.get("role", "client"),
                        "message": msg.get("message", ""),
                        "media_path": msg.get("media_path"),
                        "media_type": msg.get("media_type"),
                        "created_at": msg.get("created_at"),
                    }
                )

            elif msg_type == "presence":
                await broadcast(
                    room_id,
                    {
                        "type": "presence_update",
                        "room_id": room_id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "muted": msg.get("muted", False),
                        "in_call": msg.get("in_call", False),
                        "speaking": msg.get("speaking", False),
                        "screen_sharing": msg.get("screen_sharing", False),
                    }
                )

                await broadcast_presence(room_id)

            elif msg_type in {
                "voice_note",
                "screen_share_start",
                "screen_share_stop",
                "hangup",
                "offer",
                "answer",
                "ice-candidate",
                "call-start",
                "call-end",
            }:
                if target_id:
                    await send_to_user(room_id, target_id, msg)
                else:
                    await broadcast(room_id, msg, exclude_user_id=user_id)

            elif msg_type == "ping":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "pong",
                            "room_id": room_id,
                            "user_id": user_id,
                        }
                    )
                )

    except WebSocketDisconnect:
        room = rooms.get(room_id, {})
        room.pop(user_id, None)

        await broadcast(
            room_id,
            {
                "type": "presence_update",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "status": "offline",
            }
        )

        await broadcast_presence(room_id)

    except Exception:
        room = rooms.get(room_id, {})
        room.pop(user_id, None)
        await broadcast_presence(room_id)