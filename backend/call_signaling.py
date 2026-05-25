# call_signaling.py

import json
from fastapi import WebSocket


async def send_signal(
    ws: WebSocket,
    signal_type: str,
    room_id: str,
    user_id: str,
    target_id: str | None,
    payload: dict
):
    await ws.send_text(
        json.dumps(
            {
                "type": signal_type,
                "room_id": room_id,
                "user_id": user_id,
                "target_id": target_id,
                "payload": payload,
            }
        )
    )