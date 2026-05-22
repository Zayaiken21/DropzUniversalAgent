import asyncio
import json
from datetime import datetime
import websockets

class RealtimeClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url

    async def _send(self, payload: dict):
        async with websockets.connect(
            self.ws_url,
            open_timeout=2,
            close_timeout=2,
            ping_interval=10,
            ping_timeout=10,
        ) as ws:
            await ws.send(json.dumps(payload))

    def safe_send(self, payload: dict):
        try:
            asyncio.run(self._send(payload))
            return True
        except Exception:
            return False

    def send_chat(self, room_id, user_id, user_name, role, message, media_path=None, media_type=None):
        return self.safe_send({
            "type": "chat_message",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "role": role,
            "message": message,
            "media_path": media_path,
            "media_type": media_type,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    def send_presence(self, room_id, user_id, user_name, muted=False, in_call=False, speaking=False, screen_sharing=False):
        return self.safe_send({
            "type": "presence",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "muted": muted,
            "in_call": in_call,
            "speaking": speaking,
            "screen_sharing": screen_sharing,
        })

    def send_signal(self, payload: dict):
        return self.safe_send(payload)