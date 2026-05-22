import json
from datetime import datetime
import asyncio
import websockets

class MessageBroker:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url)

    async def send_chat(self, room_id, user_id, user_name, role, message, media_path=None, media_type=None):
        payload = {
            "type": "chat_message",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "role": role,
            "message": message,
            "media_path": media_path,
            "media_type": media_type,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        await self.ws.send(json.dumps(payload))

    async def send_presence(self, room_id, user_id, muted=False, in_call=False, speaking=False, screen_sharing=False):
        payload = {
            "type": "presence",
            "room_id": room_id,
            "user_id": user_id,
            "muted": muted,
            "in_call": in_call,
            "speaking": speaking,
            "screen_sharing": screen_sharing,
        }
        await self.ws.send(json.dumps(payload))