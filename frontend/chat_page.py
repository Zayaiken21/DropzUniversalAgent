# chat_page.py

from pathlib import Path
from datetime import datetime
from html import escape
import base64
import hashlib

from streamlit_autorefresh import st_autorefresh
import streamlit as st
import streamlit.components.v1 as components

from frontend.style_loader import load_theme_css
from frontend.realtime_client import RealtimeClient

from chat_backend.chat_db import (
    init_db,
    upsert_user,
    set_user_presence,
    set_user_muted,
    add_message,
    get_messages,
    prune_messages,
    cleanup_inactive,
    get_active_users,
    get_online_count,
)

MAX_IMAGE_PREVIEW_MB = 35
MAX_VIDEO_PREVIEW_MB = 20
MAX_VISIBLE_MESSAGES = 80


def _save_upload(upload):
    media_dir = Path("chat_backend/uploads")
    media_dir.mkdir(parents=True, exist_ok=True)
    safe_name = upload.name.replace("/", "_").replace("\\", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = media_dir / f"{stamp}_{safe_name}"
    with open(file_path, "wb") as f:
        f.write(upload.getbuffer())
    return str(file_path), upload.type


def _file_size_mb(path):
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0


def _status_icon(member):
    if member.get("muted"):
        return "🔇"
    if member.get("status") == "idle":
        return "🟡"
    return "🟢"


def _media_html(msg):
    media_path = msg.get("media_path")
    media_type = (msg.get("media_type") or "").lower()
    if not media_path:
        return ""

    path = Path(media_path)
    filename = escape(path.name)
    if not path.exists():
        return f"""
        <div class="attachment-chip">📎 {filename}</div>
        <div class="attachment-note">File is no longer available on this device.</div>
        """

    size_mb = _file_size_mb(path)
    if media_type.startswith("image/") and size_mb > MAX_IMAGE_PREVIEW_MB:
        return f"""
        <div class="attachment-chip">🖼️ {filename} · {size_mb:.1f} MB</div>
        <div class="attachment-note">Image preview disabled because this file is too large.</div>
        """

    if media_type.startswith("video/") and size_mb > MAX_VIDEO_PREVIEW_MB:
        return f"""
        <div class="attachment-chip">🎬 {filename} · {size_mb:.1f} MB</div>
        <div class="attachment-note">Video preview disabled to prevent Streamlit message-size issues.</div>
        """

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return f"""
        <div class="attachment-chip">📎 {filename}</div>
        <div class="attachment-note">File could not be previewed.</div>
        """

    if media_type.startswith("audio/"):
        return f"""
        <div class="media-card voice-card">
            <div class="voice-title">🎙️ Voice note</div>
            <audio controls preload="metadata">
                <source src="data:{media_type};base64,{encoded}" type="{media_type}">
                Your browser does not support audio playback.
            </audio>
        </div>
        """

    if media_type.startswith("image/"):
        return f"""
        <div class="media-card">
            <img class="chat-image" src="data:{media_type};base64,{encoded}" alt="{filename}" onclick="openImagePreview(this.src)" />
            <div class="media-actions">
                <button class="preview-link" onclick="openImagePreview(this.closest('.media-card').querySelector('img').src)">Open preview</button>
                <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download photo</a>
            </div>
        </div>
        """

    if media_type.startswith("video/"):
        return f"""
        <div class="media-card">
            <video class="chat-video" controls playsinline preload="metadata" onclick="event.stopPropagation();">
                <source src="data:{media_type};base64,{encoded}" type="{media_type}">
                Your browser does not support video playback.
            </video>
            <div class="media-actions">
                <button class="preview-link" onclick="openVideoPreview('data:{media_type};base64,{encoded}', '{media_type}')">Open preview</button>
                <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download video</a>
            </div>
        </div>
        """

    return f"<div class='attachment-chip'>📎 {filename}</div>"


def _build_chat_html(messages, current_user):
    bubbles = []
    for msg in messages[-MAX_VISIBLE_MESSAGES:]:
        is_me = msg.get("user_name") == current_user
        side_class = "is-me" if is_me else "is-other"
        user_name = escape(str(msg.get("user_name", "User")))
        role = escape(str(msg.get("role", "client")))
        created_at = escape(str(msg.get("created_at", "")))
        text = escape(str(msg.get("message", "") or "")).replace("\n", "<br>")
        media = _media_html(msg)
        bubbles.append(f"""
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
        """)

    body = "\n".join(bubbles)
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
html, body {{
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
    background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.055));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 18px 48px rgba(0,0,0,0.22);
    backdrop-filter: blur(18px);
}}
.chat-scroll {{
    height: 100%;
    overflow-y: auto;
    padding: 18px;
    box-sizing: border-box;
    scroll-behavior: auto;
    opacity: 0;
    transition: opacity 0.12s ease;
}}
.chat-scroll.ready {{ opacity: 1; }}
.chat-scroll::-webkit-scrollbar {{ width: 8px; }}
.chat-scroll::-webkit-scrollbar-track {{ background: transparent; }}
.chat-scroll::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.22); border-radius: 999px; }}
.msg-row {{ display: flex; margin-bottom: 12px; justify-content: flex-start; }}
.msg-bubble {{
    width: fit-content;
    max-width: 74%;
    padding: 12px 14px;
    border-radius: 18px;
    color: #f2fbff;
    text-align: left;
    background: linear-gradient(135deg, rgba(0,212,255,0.24), rgba(0,153,204,0.30));
    border: 1px solid rgba(0,212,255,0.24);
    box-shadow: 0 10px 28px rgba(0,0,0,0.16);
    box-sizing: border-box;
}}
.msg-meta {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }}
.msg-user {{ font-size: 13px; font-weight: 800; color: #ffffff; }}
.msg-role {{ font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.80); }}
.msg-time {{ font-size: 11px; color: rgba(255,255,255,0.62); }}
.msg-text {{ font-size: 14px; line-height: 1.45; color: #f7fdff; word-break: break-word; text-align: left; }}
.media-card {{ margin-top: 10px; border-radius: 14px; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.18); padding: 8px; }}
.voice-title {{ font-size: 12px; font-weight: 800; color: rgba(255,255,255,0.86); margin-bottom: 7px; }}
.media-card audio {{ display: block; width: 100%; }}
.media-card img {{ display: block; max-width: 100%; max-height: 280px; object-fit: contain; border-radius: 12px; cursor: zoom-in; }}
.media-card video {{ display: block; width: 100%; max-height: 280px; border-radius: 12px; background: rgba(0,0,0,0.35); }}
.media-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
.preview-link, .download-link {{ display: inline-flex; align-items: center; justify-content: center; padding: 7px 11px; border-radius: 999px; background: rgba(0,0,0,0.24); color: #ffffff; font-size: 12px; font-weight: 800; text-decoration: none; border: 1px solid rgba(255,255,255,0.14); cursor: pointer; }}
.attachment-chip {{ margin-top: 10px; display: inline-flex; max-width: 100%; padding: 7px 10px; border-radius: 999px; background: rgba(0,0,0,0.20); color: #ffffff; font-size: 12px; border: 1px solid rgba(255,255,255,0.12); word-break: break-word; }}
.attachment-note {{ margin-top: 7px; color: rgba(255,255,255,0.68); font-size: 11px; line-height: 1.35; }}
.preview-overlay {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,0.88); z-index: 9999; padding: 18px; box-sizing: border-box; }}
.preview-overlay.active {{ display: flex; }}
.preview-panel {{ position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }}
.preview-panel img {{ max-width: 96vw; max-height: 88vh; border-radius: 18px; object-fit: contain; box-shadow: 0 24px 80px rgba(0,0,0,0.48); }}
.preview-panel video {{ max-width: 96vw; max-height: 86vh; border-radius: 18px; background: black; box-shadow: 0 24px 80px rgba(0,0,0,0.48); }}
.close-preview {{ position: fixed; top: 18px; right: 18px; width: 44px; height: 44px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.18); background: rgba(0,0,0,0.62); color: white; font-size: 24px; font-weight: 900; cursor: pointer; z-index: 10000; }}
.jump-btn {{ position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); width: 46px; height: 46px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.25); cursor: pointer; display: none; align-items: center; justify-content: center; color: white; font-size: 22px; font-weight: 900; background: linear-gradient(135deg, #00d4ff, #0099cc); box-shadow: 0 14px 34px rgba(0,0,0,0.35), 0 0 18px rgba(0,212,255,0.38); z-index: 90; }}
.jump-btn:hover {{ transform: translateX(-50%) scale(1.06); }}
@media (max-width: 700px) {{ .chat-frame {{ height: 420px; border-radius: 20px; }} .msg-bubble {{ max-width: 88%; }} .chat-scroll {{ padding: 14px; }} }}
</style>
</head>
<body>
<div class="chat-frame">
    <div class="chat-scroll" id="chatScroll">{body}</div>
    <button class="jump-btn" id="jumpBtn" onclick="scrollToLatest()">↓</button>
</div>
<div class="preview-overlay" id="previewOverlay">
    <button class="close-preview" onclick="closePreview()">×</button>
    <div class="preview-panel" onclick="event.stopPropagation();">
        <img id="previewImage" src="" alt="Preview" style="display:none;" />
        <video id="previewVideo" controls playsinline style="display:none;"><source id="previewVideoSource" src="" type=""></video>
    </div>
</div>
<script>
const chatScroll = document.getElementById("chatScroll");
const jumpBtn = document.getElementById("jumpBtn");
const overlay = document.getElementById("previewOverlay");
const previewImage = document.getElementById("previewImage");
const previewVideo = document.getElementById("previewVideo");
const previewVideoSource = document.getElementById("previewVideoSource");
function distanceFromBottom() {{
    if (!chatScroll) return 0;
    return chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight;
}}
function updateJumpButton() {{
    if (!jumpBtn || !chatScroll) return;
    const dist = distanceFromBottom();
    jumpBtn.style.display = dist > 180 ? "flex" : "none";
    sessionStorage.setItem("dropz_chat_user_scrolled", dist > 180 ? "true" : "false");
}}
function scrollToLatest() {{
    if (!chatScroll) return;
    chatScroll.scrollTo({{ top: chatScroll.scrollHeight, behavior: "smooth" }});
    sessionStorage.setItem("dropz_chat_user_scrolled", "false");
    setTimeout(updateJumpButton, 220);
}}
function openImagePreview(src) {{
    previewVideo.pause(); previewVideo.style.display = "none"; previewVideoSource.src = "";
    previewImage.src = src; previewImage.style.display = "block"; overlay.classList.add("active");
}}
function openVideoPreview(src, type) {{
    previewImage.style.display = "none"; previewImage.src = "";
    previewVideoSource.src = src; previewVideoSource.type = type; previewVideo.load(); previewVideo.style.display = "block"; overlay.classList.add("active");
}}
function closePreview() {{
    overlay.classList.remove("active");
    previewImage.src = ""; previewImage.style.display = "none";
    previewVideo.pause(); previewVideoSource.src = ""; previewVideo.load(); previewVideo.style.display = "none";
}}
overlay.addEventListener("click", closePreview);
document.addEventListener("keydown", function(event) {{ if (event.key === "Escape") closePreview(); }});
if (chatScroll) {{
    chatScroll.addEventListener("scroll", updateJumpButton);
    requestAnimationFrame(() => {{
        const userScrolled = sessionStorage.getItem("dropz_chat_user_scrolled") === "true";
        if (!userScrolled) chatScroll.scrollTop = chatScroll.scrollHeight;
        chatScroll.classList.add("ready");
        updateJumpButton();
    }});
}}
</script>
</body>
</html>
"""


def _send_realtime_safely(rt, method_name, *args, **kwargs):
    """
    Never let the realtime websocket block or break the Streamlit chat UI.
    The database write is the source of truth; websocket is only the live nudge.
    """
    try:
        method = getattr(rt, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
    except Exception as exc:
        print(f"[CHAT REALTIME WARNING] {method_name} failed: {exc}")
    return False


def render_frontend_chat_page(voice_note=None):
    load_theme_css()

    if "pause_chat_refresh" not in st.session_state:
        st.session_state.pause_chat_refresh = False
    if "chat_muted" not in st.session_state:
        st.session_state.chat_muted = False
    if "chat_last_ping" not in st.session_state:
        st.session_state.chat_last_ping = 0.0
    if "chat_menu_open" not in st.session_state:
        st.session_state.chat_menu_open = False
    if "last_voice_note_signature" not in st.session_state:
        st.session_state.last_voice_note_signature = None

    # Chat-only mode: no calls, no screen share. Refresh is only for receiving other users' messages.
    if not st.session_state.pause_chat_refresh:
        st_autorefresh(interval=2000, key="chat_refresh")

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

    upsert_user(user_name, role)
    now = datetime.now().timestamp()
    if now - st.session_state.chat_last_ping >= 5:
        set_user_presence(
            user_name,
            1,
            "active",
            muted=int(st.session_state.chat_muted),
            in_call=0,
            screen_sharing=0,
        )
        _send_realtime_safely(
            rt,
            "send_presence",
            room_id,
            user_id,
            user_name,
            muted=st.session_state.chat_muted,
            in_call=False,
            screen_sharing=False,
        )
        st.session_state.chat_last_ping = now

    active_users = get_active_users()
    online_count = get_online_count()
    messages = get_messages(room_id=room_id, limit=MAX_VISIBLE_MESSAGES)

    st.container().markdown("### 💬 Operations Chat")
    st.caption("Secure realtime communication, voice notes, and file sharing")

    top_left, top_right = st.columns([7, 1])
    with top_left:
        st.caption(f"🟢 {online_count} online")
    with top_right:
        if st.button("⋯", key="chat_menu_toggle", width="stretch"):
            st.session_state.chat_menu_open = not st.session_state.chat_menu_open

    if st.session_state.chat_menu_open:
        with st.container(border=True):
            menu_left, menu_right = st.columns([1.2, 2.6])

            with menu_left:
                mute_label = "🔊 Unmute Chat" if st.session_state.chat_muted else "🔇 Mute Chat"
                if st.button(mute_label, key="chat_mute_toggle", width="stretch"):
                    st.session_state.chat_muted = not st.session_state.chat_muted
                    set_user_muted(user_name, int(st.session_state.chat_muted))

            with menu_right:
                st.caption("Active members")
                if active_users:
                    for member in active_users[:18]:
                        icon = _status_icon(member)
                        member_name = escape(str(member.get("name", "User")))
                        member_role = escape(str(member.get("role", "client")))
                        st.markdown(f"{icon} **{member_name}** · `{member_role}`")
                    if len(active_users) > 18:
                        st.caption(f"+ {len(active_users) - 18} more active users")
                else:
                    st.caption("No active users yet.")

    components.html(_build_chat_html(messages, user_name), height=480, scrolling=False)

    with st.form("chat_form", clear_on_submit=True):
        # text_input lets Enter/Return submit the form cleanly on desktop and mobile.
        # Shift+Enter multiline is intentionally removed for production stability.
        message = st.text_input(
            "Message",
            placeholder="Write a message...",
            label_visibility="collapsed",
        )

        c1, c2, c3 = st.columns([1.15, 1.05, 1.4])
        with c1:
            upload = st.file_uploader(
                "Upload",
                type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "webm", "pdf", "txt"],
                label_visibility="collapsed",
            )
        with c2:
            voice_note = st.audio_input("Voice", label_visibility="collapsed", width="stretch")
        with c3:
            send = st.form_submit_button("Send", width="stretch")

        if send:
            st.session_state.pause_chat_refresh = True

            media_path = None
            media_type = None
            text = message.strip() if message else ""

            if upload is not None:
                media_path, media_type = _save_upload(upload)

            if voice_note is not None:
                voice_bytes = voice_note.getvalue()
                voice_signature = hashlib.sha256(voice_bytes).hexdigest()

                if st.session_state.last_voice_note_signature != voice_signature:
                    st.session_state.last_voice_note_signature = voice_signature

                    voice_dir = Path("chat_backend/uploads/voice_notes")
                    voice_dir.mkdir(parents=True, exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    file_path = voice_dir / f"voice_{user_id}_{timestamp}.wav"

                    with open(file_path, "wb") as f:
                        f.write(voice_bytes)

                    media_path = str(file_path)
                    media_type = "audio/wav"

                    if not text:
                        text = "🎙️ Voice note"

            if text or media_path:
                add_message(user_name, role, text, media_path, media_type, room_id)
                _send_realtime_safely(
                    rt,
                    "send_chat",
                    room_id,
                    user_id,
                    user_name,
                    role,
                    text,
                    media_path,
                    media_type,
                )

            st.session_state.pause_chat_refresh = False
