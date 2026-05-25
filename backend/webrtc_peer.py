# webrtc_peer.py

from dataclasses import dataclass, field
from typing import Dict, Optional

from aiortc import RTCPeerConnection, RTCSessionDescription


@dataclass
class PeerManager:
    pcs: Dict[str, RTCPeerConnection] = field(default_factory=dict)

    async def create(self, peer_id: str, rtc_config=None):
        old_pc = self.pcs.pop(peer_id, None)

        if old_pc:
            await old_pc.close()

        pc = RTCPeerConnection(rtc_config)
        self.pcs[peer_id] = pc

        return pc

    def get(self, peer_id: str) -> Optional[RTCPeerConnection]:
        return self.pcs.get(peer_id)

    async def close(self, peer_id: str):
        pc = self.pcs.pop(peer_id, None)

        if pc:
            await pc.close()

    async def close_all(self):
        for peer_id in list(self.pcs.keys()):
            await self.close(peer_id)


peer_manager = PeerManager()


async def handle_offer(peer_id: str, offer_sdp: str, rtc_config=None):
    pc = await peer_manager.create(peer_id, rtc_config)

    offer = RTCSessionDescription(
        sdp=offer_sdp,
        type="offer"
    )

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()

    await pc.setLocalDescription(answer)

    return pc.localDescription.sdp, pc.localDescription.type


async def handle_answer(peer_id: str, answer_sdp: str):
    pc = peer_manager.get(peer_id)

    if not pc:
        return False

    answer = RTCSessionDescription(
        sdp=answer_sdp,
        type="answer"
    )

    await pc.setRemoteDescription(answer)

    return True