from dataclasses import dataclass, field
from typing import Dict

from aiortc import RTCPeerConnection, RTCSessionDescription

@dataclass
class PeerManager:
    pcs: Dict[str, RTCPeerConnection] = field(default_factory=dict)

    async def create(self, peer_id: str, rtc_config):
        pc = RTCPeerConnection(rtc_config)
        self.pcs[peer_id] = pc
        return pc

    async def close(self, peer_id: str):
        pc = self.pcs.pop(peer_id, None)
        if pc:
            await pc.close()

peer_manager = PeerManager()

async def handle_offer(peer_id: str, offer_sdp: str, rtc_config):
    pc = await peer_manager.create(peer_id, rtc_config)
    offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return pc.localDescription.sdp, pc.localDescription.type

async def handle_answer(peer_id: str, answer_sdp: str):
    pc = peer_manager.pcs.get(peer_id)
    if not pc:
        return False
    answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
    await pc.setRemoteDescription(answer)
    return True