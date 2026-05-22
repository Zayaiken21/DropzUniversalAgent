import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
from frontend.realtime_client import RealtimeClient

def render_call_controls(user_id, user_name, room_id, ws_url):
    client = RealtimeClient(ws_url)
    rtc_config = RTCConfiguration(
        [{"urls": ["stun:stun.l.google.com:19302"]}]
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("📞 Join", use_container_width=True):
            st.session_state.in_call = True
            client.send_presence(room_id, user_id, user_name, in_call=True)

    with c2:
        if st.button("🔇 Mute", use_container_width=True):
            st.session_state.call_muted = not st.session_state.get("call_muted", False)
            client.send_presence(room_id, user_id, user_name, muted=st.session_state.call_muted, in_call=True)

    with c3:
        if st.button("🖥 Share", use_container_width=True):
            st.session_state.screen_share_active = True
            client.send_signal({
                "type": "screen_share_start",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
            })

    with c4:
        if st.button("⛔ Leave", use_container_width=True):
            st.session_state.in_call = False
            st.session_state.screen_share_active = False
            client.send_presence(room_id, user_id, user_name, in_call=False, muted=False, screen_sharing=False)
            client.send_signal({
                "type": "hangup",
                "room_id": room_id,
                "user_id": user_id,
                "user_name": user_name,
            })

    st.markdown("### Call media")
    webrtc_streamer(
        key=f"call_{room_id}_{user_id}",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=rtc_config,
        media_stream_constraints={"audio": True, "video": True},
    )