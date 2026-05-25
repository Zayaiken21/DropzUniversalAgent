# realtime_client.py

import asyncio
import json
import threading
from datetime import datetime

import websockets


class RealtimeClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url

    async def _send(self, payload: dict):
        async with websockets.connect(
            self.ws_url,
            open_timeout=0.8,
            close_timeout=0.8,
            ping_interval=None,
            max_size=None,
        ) as ws:
            await ws.send(json.dumps(payload))

    def safe_send(self, payload: dict):
        def runner():
            try:
                asyncio.run(self._send(payload))
            except Exception:
                pass

        thread = threading.Thread(
            target=runner,
            daemon=True
        )

        thread.start()

        return True

    def send_chat(
        self,
        room_id,
        user_id,
        user_name,
        role,
        message,
        media_path=None,
        media_type=None
    ):
        return self.safe_send(
            {
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
        )

    def send_presence(
        self,
        room_id,
        user_id,
        user_name,
        muted=False,
        in_call=False,
        speaking=False,
        screen_sharing=False
    ):
        return self.safe_send(
            {
                "type": "presence",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "muted": muted,
                "in_call": in_call,
                "speaking": speaking,
                "screen_sharing": screen_sharing,
            }
        )

    def send_join(self, room_id, user_id, user_name):
        return self.safe_send(
            {
                "type": "join",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
            }
        )

    def send_signal(self, payload: dict):
        return self.safe_send(payload)

    def send_offer(self, room_id, user_id, user_name, target_id, offer):
        return self.safe_send(
            {
                "type": "offer",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "target_id": target_id,
                "payload": offer,
            }
        )

    def send_answer(self, room_id, user_id, user_name, target_id, answer):
        return self.safe_send(
            {
                "type": "answer",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "target_id": target_id,
                "payload": answer,
            }
        )

    def send_ice_candidate(
        self,
        room_id,
        user_id,
        user_name,
        target_id,
        candidate
    ):
        return self.safe_send(
            {
                "type": "ice-candidate",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "target_id": target_id,
                "payload": candidate,
            }
        )

    def send_hangup(self, room_id, user_id, user_name, target_id=None):
        return self.safe_send(
            {
                "type": "hangup",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
                "target_id": target_id,
            }
        )