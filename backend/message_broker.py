# message_broker.py

import json
from datetime import datetime

import websockets


class MessageBroker:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None

    async def connect(self):
        if self.ws:
            return self.ws

        self.ws = await websockets.connect(
            self.ws_url,
            open_timeout=2,
            close_timeout=2,
            ping_interval=10,
            ping_timeout=10,
            max_size=None,
        )

        return self.ws

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def send(self, payload: dict):
        ws = await self.connect()

        try:
            await ws.send(json.dumps(payload))

        except Exception:
            self.ws = None
            ws = await self.connect()
            await ws.send(json.dumps(payload))

    async def send_chat(
        self,
        room_id,
        user_id,
        user_name,
        role,
        message,
        media_path=None,
        media_type=None
    ):
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

        await self.send(payload)

    async def send_presence(
        self,
        room_id,
        user_id,
        user_name="Guest",
        muted=False,
        in_call=False,
        speaking=False,
        screen_sharing=False
    ):
        payload = {
            "type": "presence",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "muted": muted,
            "in_call": in_call,
            "speaking": speaking,
            "screen_sharing": screen_sharing,
        }

        await self.send(payload)

    async def send_signal(self, payload: dict):
        await self.send(payload)