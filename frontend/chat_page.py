# chat_page.py

from pathlib import Path
from datetime import datetime
from html import escape
import base64

import streamlit as st
import streamlit.components.v1 as components

from frontend.style_loader import load_theme_css
from frontend.realtime_client import RealtimeClient

from chat_backend.chat_db import (
    init_db,
    upsert_user,
    set_user_presence,
    mark_user_offline,
    set_user_muted,
    add_message,
    get_messages,
    prune_messages,
    cleanup_inactive,
    get_active_users,
    get_online_count,
)


MAX_EMBED_MB = 35


def _save_upload(upload):
    media_dir = Path("chat_backend/uploads")
    media_dir.mkdir(parents=True, exist_ok=True)

    safe_name = upload.name.replace("/", "_").replace("\\", "_")
    file_path = media_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(upload.getbuffer())

    return str(file_path), upload.type


def _status_icon(member):
    if member.get("in_call"):
        return "📞"
    if member.get("muted"):
        return "🔇"
    if member.get("status") == "idle":
        return "🟡"
    return "🟢"


def _file_size_mb(path):
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0


def _media_html(msg):
    media_path = msg.get("media_path")
    media_type = (msg.get("media_type") or "").lower()

    if not media_path:
        return ""

    path = Path(media_path)
    filename = escape(path.name)

    if not path.exists():
        return f"""
        <div class="attachment-chip">
            📎 {filename}
        </div>
        """

    size_mb = _file_size_mb(path)

    if size_mb > MAX_EMBED_MB:
        return f"""
        <div class="attachment-chip">
            📎 {filename} · {size_mb:.1f} MB
        </div>

        <div class="attachment-note">
            Preview disabled for large files to prevent Streamlit’s 200MB message limit.
        </div>
        """

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return f"""
        <div class="attachment-chip">
            📎 {filename}
        </div>
        """

    if media_type.startswith("image/"):
        return f"""
        <div class="media-card">
            <img src="data:{media_type};base64,{encoded}" alt="{filename}" />

            <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">
                Download photo
            </a>
        </div>
        """

    if media_type.startswith("video/"):
        return f"""
        <div class="media-card">
            <video controls playsinline preload="metadata">
                <source src="data:{media_type};base64,{encoded}" type="{media_type}">
                Your browser does not support video playback.
            </video>

            <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">
                Download video
            </a>
        </div>
        """

    return f"""
    <div class="attachment-chip">
        📎 {filename}
    </div>
    """


def _build_chat_html(messages, current_user):
    bubbles = []

    for msg in messages[-140:]:
        is_me = msg.get("user_name") == current_user
        side_class = "is-me" if is_me else "is-other"

        user_name = escape(str(msg.get("user_name", "User")))
        role = escape(str(msg.get("role", "client")))
        created_at = escape(str(msg.get("created_at", "")))
        text = escape(str(msg.get("message", "") or "")).replace("\n", "<br>")

        media = _media_html(msg)

        bubble = f"""
        <div class="msg-row {side_class}">
            <div class="msg-bubble">
                <div class="msg-meta">
                    <span class="msg-user">{user_name}</span>
                    <span class="msg-role">{role}</span>
                    <span class="msg-time">{created_at}</span>
                </div>

                {"<div class='msg-text'>" + text + "</div>" if text else ""}

                {media}
            </div>
        </div>
        """

        bubbles.append(bubble)

    body = "\n".join(bubbles)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8" />

        <style>
            html,
            body {{
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                overflow: hidden;
            }}

            .chat-frame {{
                position: relative;
                height: 460px;
                border-radius: 24px;
                overflow: hidden;
                background:
                    linear-gradient(
                        180deg,
                        rgba(255,255,255,0.10),
                        rgba(255,255,255,0.055)
                    );
                border: 1px solid rgba(255,255,255,0.14);
                box-shadow: 0 18px 48px rgba(0,0,0,0.22);
                backdrop-filter: blur(18px);
            }}

            .chat-scroll {{
                height: 100%;
                overflow-y: auto;
                padding: 18px;
                box-sizing: border-box;
                scroll-behavior: smooth;
            }}

            .chat-scroll::-webkit-scrollbar {{
                width: 8px;
            }}

            .chat-scroll::-webkit-scrollbar-track {{
                background: transparent;
            }}

            .chat-scroll::-webkit-scrollbar-thumb {{
                background: rgba(255,255,255,0.22);
                border-radius: 999px;
            }}

            .msg-row {{
                display: flex;
                margin-bottom: 12px;
            }}

            .msg-row.is-me,
            .msg-row.is-other {{
                justify-content: flex-start;
            }}

            .msg-bubble {{
                width: fit-content;
                max-width: 74%;
                padding: 12px 14px;
                border-radius: 18px;
                color: #f2fbff;
                text-align: left;
                background:
                    linear-gradient(
                        135deg,
                        rgba(0,212,255,0.24),
                        rgba(0,153,204,0.30)
                    );
                border: 1px solid rgba(0,212,255,0.24);
                box-shadow: 0 10px 28px rgba(0,0,0,0.16);
                box-sizing: border-box;
            }}

            .msg-meta {{
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: 8px;
                flex-wrap: wrap;
                margin-bottom: 6px;
            }}

            .msg-user {{
                font-size: 13px;
                font-weight: 800;
                color: #ffffff;
            }}

            .msg-role {{
                font-size: 11px;
                font-weight: 700;
                padding: 2px 7px;
                border-radius: 999px;
                background: rgba(255,255,255,0.12);
                color: rgba(255,255,255,0.80);
            }}

            .msg-time {{
                font-size: 11px;
                color: rgba(255,255,255,0.62);
            }}

            .msg-text {{
                font-size: 14px;
                line-height: 1.45;
                color: #f7fdff;
                word-break: break-word;
                text-align: left;
            }}

            .media-card {{
                margin-top: 10px;
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.12);
                background: rgba(0,0,0,0.18);
                padding: 8px;
            }}

            .media-card img {{
                display: block;
                max-width: 100%;
                max-height: 280px;
                object-fit: contain;
                border-radius: 12px;
            }}

            .media-card video {{
                display: block;
                width: 100%;
                max-height: 280px;
                border-radius: 12px;
                background: rgba(0,0,0,0.35);
            }}

            .download-link {{
                display: inline-flex;
                margin: 10px 0 2px 0;
                padding: 7px 11px;
                border-radius: 999px;
                background: rgba(0,0,0,0.24);
                color: #ffffff;
                font-size: 12px;
                font-weight: 800;
                text-decoration: none;
                border: 1px solid rgba(255,255,255,0.14);
            }}

            .attachment-chip {{
                margin-top: 10px;
                display: inline-flex;
                max-width: 100%;
                padding: 7px 10px;
                border-radius: 999px;
                background: rgba(0,0,0,0.20);
                color: #ffffff;
                font-size: 12px;
                border: 1px solid rgba(255,255,255,0.12);
                word-break: break-word;
            }}

            .attachment-note {{
                margin-top: 7px;
                color: rgba(255,255,255,0.68);
                font-size: 11px;
                line-height: 1.35;
            }}

            .jump-btn {{
                position: absolute;
                right: 16px;
                bottom: 16px;
                width: 42px;
                height: 42px;
                border-radius: 999px;
                border: 0;
                cursor: pointer;
                display: none;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 20px;
                font-weight: 800;
                background: linear-gradient(135deg, #00d4ff, #0099cc);
                box-shadow: 0 12px 28px rgba(0,0,0,0.30);
            }}

            @media (max-width: 700px) {{
                .chat-frame {{
                    height: 420px;
                    border-radius: 20px;
                }}

                .msg-bubble {{
                    max-width: 88%;
                }}

                .chat-scroll {{
                    padding: 14px;
                }}
            }}
        </style>
    </head>

    <body>
        <div class="chat-frame">
            <div class="chat-scroll" id="chatScroll">
                {body}
            </div>

            <button class="jump-btn" id="jumpBtn" onclick="scrollToLatest()">↓</button>
        </div>

        <script>
            const chatScroll = document.getElementById("chatScroll");
            const jumpBtn = document.getElementById("jumpBtn");

            function distanceFromBottom() {{
                return chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight;
            }}

            function updateJumpButton() {{
                if (distanceFromBottom() > 260) {{
                    jumpBtn.style.display = "flex";
                }} else {{
                    jumpBtn.style.display = "none";
                }}
            }}

            function scrollToLatest() {{
                chatScroll.scrollTo({{
                    top: chatScroll.scrollHeight,
                    behavior: "smooth"
                }});
            }}

            chatScroll.addEventListener("scroll", updateJumpButton);

            setTimeout(() => {{
                chatScroll.scrollTop = chatScroll.scrollHeight;
                updateJumpButton();
            }}, 80);
        </script>
    </body>
    </html>
    """


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

    ws_url = st.session_state.get(
        "ws_url",
        "ws://127.0.0.1:8001/ws/chat"
    )

    rt = RealtimeClient(ws_url)

    defaults = {
        "chat_menu_open": False,
        "chat_muted": False,
        "chat_in_call": False,
        "chat_last_ping": 0.0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    upsert_user(user_name, role)

    now = datetime.now().timestamp()

    if now - st.session_state.chat_last_ping >= 5:
        status = "sharing" if st.session_state.chat_in_call else "active"

        set_user_presence(
            user_name,
            1,
            status,
            muted=int(st.session_state.chat_muted),
            in_call=int(st.session_state.chat_in_call)
        )

        rt.send_presence(
            room_id,
            user_id,
            user_name,
            muted=st.session_state.chat_muted,
            in_call=st.session_state.chat_in_call
        )

        st.session_state.chat_last_ping = now

    active_users = get_active_users()
    online_count = get_online_count()

    messages = get_messages(
        room_id=room_id,
        limit=300
    )

    st.container().markdown("### 💬 Operations Chat")
    st.caption("Secure realtime communication & collaboration")

    top_left, top_right = st.columns([7, 1])

    with top_left:
        st.caption(f"🟢 {online_count} online")

    with top_right:
        if st.button("⋯", key="chat_menu_toggle", use_container_width=True):
            st.session_state.chat_menu_open = not st.session_state.chat_menu_open
            st.rerun()

    if st.session_state.chat_menu_open:
        with st.container(border=True):
            m1, m2 = st.columns(2)

            with m1:
                mute_label = "🔊 Unmute Chat" if st.session_state.chat_muted else "🔇 Mute Chat"

                if st.button(mute_label, key="chat_mute_toggle", use_container_width=True):
                    st.session_state.chat_muted = not st.session_state.chat_muted

                    set_user_muted(
                        user_name,
                        int(st.session_state.chat_muted)
                    )

                    st.rerun()

            with m2:
                call_label = "❌ Leave Call" if st.session_state.chat_in_call else "📞 Join Call"

                if st.button(call_label, key="chat_call_toggle", use_container_width=True):
                    st.session_state.chat_in_call = not st.session_state.chat_in_call

                    call_text = (
                        f"📞 {user_name} joined the call."
                        if st.session_state.chat_in_call
                        else f"📞 {user_name} left the call."
                    )

                    add_message(
                        user_name,
                        role,
                        call_text,
                        None,
                        None,
                        room_id
                    )

                    rt.send_chat(
                        room_id,
                        user_id,
                        user_name,
                        role,
                        call_text,
                        None,
                        None
                    )

                    st.rerun()

            st.caption("Active team")

            for member in active_users:
                icon = _status_icon(member)
                member_name = member.get("name", "User")
                member_role = member.get("role", "client")

                st.write(f"{icon} **{member_name}** · {member_role}")

    chat_html = _build_chat_html(
        messages,
        user_name
    )

    components.html(
        chat_html,
        height=480,
        scrolling=False
    )

    with st.form("chat_form", clear_on_submit=True):
        message = st.text_area(
            "Message",
            placeholder="Write a message...",
            label_visibility="collapsed",
            height=78
        )

        c1, c2, c3 = st.columns([1, 1, 4])

        with c1:
            upload = st.file_uploader(
                "Upload",
                type=[
                    "png",
                    "jpg",
                    "jpeg",
                    "gif",
                    "mp4",
                    "mov",
                    "webm",
                    "pdf",
                    "txt",
                ],
                label_visibility="collapsed"
            )

        with c2:
            voice = st.form_submit_button(
                "🎙",
                use_container_width=True
            )

        with c3:
            send = st.form_submit_button(
                "Send",
                use_container_width=True
            )

        if send:
            media_path = None
            media_type = None

            text = message.strip() if message else ""

            if upload is not None:
                media_path, media_type = _save_upload(upload)

            if text or media_path:
                add_message(
                    user_name,
                    role,
                    text,
                    media_path,
                    media_type,
                    room_id
                )

                rt.send_chat(
                    room_id,
                    user_id,
                    user_name,
                    role,
                    text,
                    media_path,
                    media_type
                )

                st.rerun()

        if voice:
            st.info("Voice note path is wired through the realtime client and server signals.")