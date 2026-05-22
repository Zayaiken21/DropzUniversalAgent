import streamlit as st
from aiortc.contrib.media import MediaRecorder
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

from frontend.realtime_client import RealtimeClient

def render_voice_note_widget(user_id, user_name, room_id, ws_url):
    client = RealtimeClient(ws_url)

    st.markdown("### Voice note")
    c1, c2 = st.columns([1, 1])

    with c1:
        start = st.button("🎙 Start voice note", use_container_width=True)
    with c2:
        stop = st.button("⏹ Stop voice note", use_container_width=True)

    if start:
        client.send_signal({
            "type": "voice_note",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "payload": {"status": "start"}
        })
        st.session_state.voice_note_active = True

    if stop:
        client.send_signal({
            "type": "voice_note",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
            "payload": {"status": "stop"}
        })
        st.session_state.voice_note_active = False

    if st.session_state.get("voice_note_active", False):
        webrtc_streamer(
            key=f"voice_note_{room_id}_{user_id}",
            mode=WebRtcMode.SENDONLY,
            client_settings=ClientSettings(
                rtc_configuration=RTCConfiguration(
                    [{"urls": ["stun:stun.l.google.com:19302"]}]
                ),
                media_stream_constraints={"audio": True, "video": False},
            ),
            in_recorder_factory=lambda: MediaRecorder(f"chat_backend/uploads/voice_note_{user_id}.wav"),
        )