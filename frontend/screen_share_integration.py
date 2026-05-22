import streamlit as st
from frontend.realtime_client import RealtimeClient

def render_screen_share_button(user_id, user_name, room_id, ws_url):
    client = RealtimeClient(ws_url)

    c1, c2 = st.columns([1, 1])
    with c1:
        start = st.button("🖥 Start screen share", use_container_width=True)
    with c2:
        stop = st.button("⛔ Stop screen share", use_container_width=True)

    if start:
        client.send_signal({
            "type": "screen_share_start",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
        })
        st.session_state.screen_share_active = True

    if stop:
        client.send_signal({
            "type": "screen_share_stop",
            "room_id": room_id,
            "user_id": user_id,
            "user_name": user_name,
        })
        st.session_state.screen_share_active = False