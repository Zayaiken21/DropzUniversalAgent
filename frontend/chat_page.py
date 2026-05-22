from pathlib import Path
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

from frontend.style_loader import load_theme_css
from frontend.realtime_client import RealtimeClient
from chat_backend.chat_db import (
    init_db, upsert_user, set_user_presence, mark_user_offline, set_user_muted,
    add_message, get_messages, prune_messages, cleanup_inactive,
    get_active_users, get_online_count
)

def _save_upload(upload):
    media_dir = Path("chat_backend/uploads")
    media_dir.mkdir(parents=True, exist_ok=True)
    file_path = media_dir / upload.name
    with open(file_path, "wb") as f:
        f.write(upload.getbuffer())
    return str(file_path), upload.type

def _status_dot(status):
    if status == "speaking":
        return "🔵"
    if status == "sharing":
        return "📺"
    if status == "idle":
        return "🟡"
    return "🟢"

def _render_message(msg, idx):
    st.markdown('<div class="chat-message">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="chat-meta"><strong>{msg["user_name"]}</strong> • {msg["role"]} • {msg["created_at"]}</div>',
        unsafe_allow_html=True
    )

    if msg.get("message"):
        st.markdown(msg["message"])

    if msg.get("media_path"):
        mt = (msg.get("media_type") or "").lower()
        media_path = msg["media_path"]

        if mt.startswith("image/"):
            st.image(media_path, use_container_width=True)

        elif mt.startswith("video/"):
            st.video(media_path)

        else:
            with open(media_path, "rb") as f:
                st.download_button(
                    "Download attachment",
                    data=f.read(),
                    file_name=Path(media_path).name,
                    use_container_width=True,
                    key=f"download_{msg['id']}_{idx}"
                )

    st.markdown("</div>", unsafe_allow_html=True)

def render_frontend_chat_page():
    load_theme_css()
    init_db()
    cleanup_inactive(minutes=1)
    prune_messages()

    user = st.session_state.get("user", {})
    user_name = user.get("name", "Guest")
    role = user.get("role", "client")
    user_id = str(user.get("id", user_name))
    room_id = "main"
    ws_url = st.session_state.get("ws_url", "ws://127.0.0.1:8001/ws/chat")
    rt = RealtimeClient(ws_url)

    for k, v in {
        "chat_more_menu": False,
        "chat_notice": True,
        "chat_mute": False,
        "chat_last_ping": 0.0,
        "chat_live_edge": True,
        "open_image_path": None,
        "in_call": False,
        "signed_out": False,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.signed_out:
        mark_user_offline(user_name)
        st.info("You signed out.")
        return

    upsert_user(user_name, role)

    now = datetime.now().timestamp()
    if now - st.session_state.chat_last_ping >= 5:
        set_user_presence(user_name, 1, "active", muted=int(st.session_state.chat_mute), in_call=int(st.session_state.in_call))
        rt.send_presence(room_id, user_id, user_name, muted=st.session_state.chat_mute, in_call=st.session_state.in_call)
        st.session_state.chat_last_ping = now

    active_users = get_active_users()
    online_count = get_online_count()
    messages = get_messages(room_id=room_id, limit=300)

    st.markdown('<div class="chat-shell">', unsafe_allow_html=True)

    st.markdown('<div class="chat-top">', unsafe_allow_html=True)
    title_col, online_col, menu_col = st.columns([5, 1.2, 0.9])

    with title_col:
        st.markdown('<div class="chat-brand">💬 Operations Chat</div><div class="chat-sub">Real-time team messaging and live presence</div>', unsafe_allow_html=True)
    with online_col:
        st.markdown(f'<div class="online-pill">Online: {online_count}</div>', unsafe_allow_html=True)
    with menu_col:
        if st.button("⋯", use_container_width=True):
            st.session_state.chat_more_menu = not st.session_state.chat_more_menu
            st.rerun()

    if st.session_state.chat_more_menu:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔔 On" if st.session_state.chat_notice else "🔕 Off", use_container_width=True):
                st.session_state.chat_notice = not st.session_state.chat_notice
                st.rerun()
        with c2:
            if st.button("Sign out", use_container_width=True):
                mark_user_offline(user_name)
                st.session_state.signed_out = True
                st.rerun()

        st.markdown("### Active Users")
        for member in active_users:
            st.markdown(
                f'**{_status_dot(member.get("status", "active"))} {member["name"]}**  \n'
                f'<span class="soft-muted">{member.get("status", "active")}</span>',
                unsafe_allow_html=True
            )

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="messages-shell">', unsafe_allow_html=True)
    st.markdown('<div class="messages-box" id="chat_messages_box">', unsafe_allow_html=True)

    for i, msg in enumerate(messages[-140:]):
        _render_message(msg, i)

    st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown('<div class="compose">', unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        st.markdown('<div class="composer-card">', unsafe_allow_html=True)
        st.markdown("### Send message", unsafe_allow_html=True)

        message = st.text_area("Message", placeholder="Write a message...", label_visibility="collapsed", height=92)

        b1, b2, b3 = st.columns([1, 1, 3])

        with b1:
            upload = st.file_uploader("🖼", type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "webm", "pdf", "txt"], label_visibility="collapsed")
        with b2:
            voice = st.form_submit_button("🎙", use_container_width=True)
        with b3:
            send = st.form_submit_button("Send", use_container_width=True)

        if send:
            media_path = None
            media_type = None
            msg_text = message.strip() if message else ""
            if upload is not None:
                media_path, media_type = _save_upload(upload)
            if msg_text or media_path:
                add_message(user_name, role, msg_text, media_path, media_type, room_id)
                rt.send_chat(room_id, user_id, user_name, role, msg_text, media_path, media_type)
                st.session_state.chat_live_edge = True
                st.rerun()

        if voice:
            st.info("Voice note path is wired through the realtime client and server signals.")

        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    components.html("""
    <script>
    const box = window.parent.document.querySelector('#chat_messages_box');
    if (box) box.scrollTop = box.scrollHeight;
    </script>
    """, height=0)

    st.markdown("</div>", unsafe_allow_html=True)