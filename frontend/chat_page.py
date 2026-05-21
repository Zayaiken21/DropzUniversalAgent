from pathlib import Path
import streamlit as st

from frontend.style_loader import load_theme_css
from chat_backend.chat_db import (
    init_db, upsert_user, set_user_presence, set_user_muted,
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
            st.markdown(
                f"""
                <div class="chat-media-wrap">
                    <img src="file://{Path(media_path).resolve().as_posix()}"
                         class="chat-image-preview"
                         alt="chat image {idx}" />
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open image", key=f"open_image_{msg['id']}_{idx}", use_container_width=False):
                st.session_state.open_image_path = media_path

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
    cleanup_inactive()
    prune_messages()

    user = st.session_state.get("user", {})
    user_name = user.get("name", "Guest")
    role = user.get("role", "client")
    room_id = "main"

    upsert_user(user_name, role)
    set_user_presence(user_name, 1, "active")

    if "chat_more_menu" not in st.session_state:
        st.session_state.chat_more_menu = False
    if "chat_notice" not in st.session_state:
        st.session_state.chat_notice = True
    if "chat_mute" not in st.session_state:
        st.session_state.chat_mute = False
    if "open_image_path" not in st.session_state:
        st.session_state.open_image_path = None

    active_users = get_active_users()
    online_count = get_online_count()
    messages = get_messages(room_id=room_id, limit=300)

    st.markdown('<div class="chat-shell">', unsafe_allow_html=True)

    st.markdown('<div class="chat-top">', unsafe_allow_html=True)
    title_col, online_col, menu_col = st.columns([5, 1.2, 0.9])

    with title_col:
        st.markdown(
            """
            <div class="chat-title-wrap">
                <div class="chat-brand">💬 Operations Chat</div>
                <div class="chat-sub">Real-time team messaging and live presence</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with online_col:
        st.markdown(f'<div class="online-pill">Online: {online_count}</div>', unsafe_allow_html=True)

    with menu_col:
        if st.button("⋯", help="Chat options", use_container_width=True):
            st.session_state.chat_more_menu = not st.session_state.chat_more_menu
            st.rerun()

    if st.session_state.chat_more_menu:
        opt1, opt2, opt3 = st.columns([1, 1, 1])
        with opt1:
            if st.button("🔔 On" if st.session_state.chat_notice else "🔕 Off", use_container_width=True):
                st.session_state.chat_notice = not st.session_state.chat_notice
                st.rerun()
        with opt2:
            if st.button("Mute" if not st.session_state.chat_mute else "Unmute", use_container_width=True):
                st.session_state.chat_mute = not st.session_state.chat_mute
                set_user_muted(user_name, 1 if st.session_state.chat_mute else 0)
                st.rerun()
        with opt3:
            if st.button("Users", use_container_width=True):
                st.session_state.chat_more_menu = False
                st.rerun()

        st.markdown('<div class="members-card chat-options-panel">', unsafe_allow_html=True)
        st.markdown("### Active Users")
        for member in active_users:
            st.markdown(
                f'**{_status_dot(member.get("status", "active"))} {member["name"]}**  \n'
                f'<span class="soft-muted">{member.get("status", "active")}</span>',
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="chat-grid">', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="activity-card drawer">', unsafe_allow_html=True)
        st.markdown("### Quick Status")
        st.markdown("• Realtime presence\n• Internal scroll\n• Image preview\n• Call controls")
        st.markdown("</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="messages-box">', unsafe_allow_html=True)

        if st.session_state.open_image_path:
            st.markdown('<div class="composer-card image-viewer-card">', unsafe_allow_html=True)
            st.image(st.session_state.open_image_path, use_container_width=True)
            if st.button("✕ Close image", key="close_image_viewer", use_container_width=True):
                st.session_state.open_image_path = None
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        for i, msg in enumerate(messages[-140:]):
            _render_message(msg, i)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="jump-latest">', unsafe_allow_html=True)
        if st.button("↓", key="jump_to_latest", use_container_width=True):
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="compose">', unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            st.markdown('<div class="composer-card">', unsafe_allow_html=True)
            st.markdown("### Send message", unsafe_allow_html=True)

            message = st.text_area(
                "Message",
                placeholder="Write a message...",
                label_visibility="collapsed",
                height=92
            )

            b1, b2, b3, b4 = st.columns([0.62, 0.72, 0.72, 2.4])

            with b1:
                upload = st.file_uploader("🖼", type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "webm", "pdf", "txt"], label_visibility="collapsed")
            with b2:
                voice = st.form_submit_button("🎙", use_container_width=True)
            with b3:
                call = st.form_submit_button("📞", use_container_width=True)
            with b4:
                send = st.form_submit_button("Send", use_container_width=True)

            if send:
                media_path = None
                media_type = None
                if upload is not None:
                    media_path, media_type = _save_upload(upload)
                msg_text = message.strip() if message else ""
                if msg_text or media_path:
                    add_message(
                        user_name=user_name,
                        role=role,
                        message=msg_text,
                        media_path=media_path,
                        media_type=media_type,
                        room_id=room_id,
                    )
                    if not st.session_state.chat_mute and st.session_state.chat_notice:
                        st.toast("New message sent", icon="🔔")
                    st.rerun()

            if voice:
                st.info("Connect voice capture to streamlit-webrtc or your audio backend.")
            if call:
                st.info("Connect call/join/leave to your persistent WebRTC signaling backend.")

            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)