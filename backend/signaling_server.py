import json
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@dataclass
class Conn:
    websocket: WebSocket
    user_name: str
    user_id: str
    room_id: str

rooms: Dict[str, Dict[str, Conn]] = {}

async def broadcast(room_id: str, payload: dict, exclude_user_id: Optional[str] = None):
    payload_text = json.dumps(payload)
    room = rooms.get(room_id, {})
    dead = []
    for uid, conn in room.items():
        if exclude_user_id and uid == exclude_user_id:
            continue
        try:
            await conn.websocket.send_text(payload_text)
        except Exception:
            dead.append(uid)
    for uid in dead:
        room.pop(uid, None)

@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    user_name = "Guest"
    user_id = str(id(websocket))
    room_id = "main"

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            user_name = msg.get("user_name", user_name)
            user_id = msg.get("user_id", user_id)
            room_id = msg.get("room_id", room_id)

            rooms.setdefault(room_id, {})[user_id] = Conn(websocket, user_name, user_id, room_id)

            if msg_type == "chat_message":
                await broadcast(room_id, {
                    "type": "chat_message",
                    "room_id": room_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "role": msg.get("role", "client"),
                    "message": msg.get("message", ""),
                    "media_path": msg.get("media_path"),
                    "media_type": msg.get("media_type"),
                    "created_at": msg.get("created_at"),
                })

            elif msg_type == "presence":
                await broadcast(room_id, {
                    "type": "presence_update",
                    "room_id": room_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "muted": msg.get("muted", False),
                    "in_call": msg.get("in_call", False),
                    "speaking": msg.get("speaking", False),
                    "screen_sharing": msg.get("screen_sharing", False),
                }, exclude_user_id=user_id)

            elif msg_type in {"voice_note", "screen_share_start", "screen_share_stop", "hangup", "offer", "answer", "ice-candidate"}:
                await broadcast(room_id, msg, exclude_user_id=user_id)

    except WebSocketDisconnect:
        room = rooms.get(room_id, {})
        room.pop(user_id, None)
        await broadcast(room_id, {
            "type": "presence_update",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "status": "offline",
        })