from pathlib import Path
from html import escape
import base64
import hashlib
import time

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

try:
    from frontend.style_loader import load_theme_css
except Exception:
    def load_theme_css():
        return None

from chat_backend.chat_db import (
    init_db,
    upsert_user,
    set_user_presence,
    set_user_muted,
    add_message,
    get_messages,
    get_latest_message_id,
    prune_messages,
    cleanup_inactive,
    get_active_users,
    get_online_count,
)
from chat_backend.chat_media import save_upload
from chat_backend.chat_time import to_est_label

MAX_IMAGE_PREVIEW_MB = 25
MAX_VIDEO_PREVIEW_MB = 18
MAX_VISIBLE_MESSAGES = 90
REFRESH_MS = 1600
ROOM_ID = "main"


def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _file_size_mb(path):
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0


def _status_icon(member):
    if int(member.get("muted") or 0) == 1:
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
        <div class="attachment-note">File is no longer available on this computer/server.</div>
        """

    size_mb = _file_size_mb(path)
    if media_type.startswith("image/") and size_mb > MAX_IMAGE_PREVIEW_MB:
        return f"""
        <div class="attachment-chip">🖼️ {filename} · {size_mb:.1f} MB</div>
        <div class="attachment-note">Preview disabled for large image. File saved successfully.</div>
        """

    if media_type.startswith("video/") and size_mb > MAX_VIDEO_PREVIEW_MB:
        return f"""
        <div class="attachment-chip">🎬 {filename} · {size_mb:.1f} MB</div>
        <div class="attachment-note">Preview disabled for large video to keep chat fast.</div>
        """

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return f"""
        <div class="attachment-chip">📎 {filename}</div>
        <div class="attachment-note">File saved, but preview could not load.</div>
        """

    if media_type.startswith("audio/"):
        return f"""
        <div class="media-card voice-card">
            <div class="voice-title">🎙️ Voice note</div>
            <audio controls preload="metadata">
                <source src="data:{media_type};base64,{encoded}" type="{media_type}">
            </audio>
        </div>
        """

    if media_type.startswith("image/"):
        return f"""
        <div class="media-card">
            <img class="chat-image" src="data:{media_type};base64,{encoded}" alt="{filename}" onclick="openImagePreview(this.src)" />
            <div class="media-actions">
                <button class="preview-link" onclick="openImagePreview(this.closest('.media-card').querySelector('img').src)">Preview</button>
                <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download</a>
            </div>
        </div>
        """

    if media_type.startswith("video/"):
        return f"""
        <div class="media-card">
            <video class="chat-video" controls playsinline preload="metadata">
                <source src="data:{media_type};base64,{encoded}" type="{media_type}">
            </video>
            <div class="media-actions">
                <button class="preview-link" onclick="openVideoPreview('data:{media_type};base64,{encoded}', '{media_type}')">Preview</button>
                <a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download</a>
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
        created_at = escape(to_est_label(str(msg.get("created_at", ""))))
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

    body = "\n".join(bubbles) if bubbles else """
        <div class="empty-chat">
            <div class="empty-icon">💬</div>
            <div class="empty-title">No messages yet</div>
            <div class="empty-subtitle">Send the first message and everyone connected to this Streamlit app will see it.</div>
        </div>
    """

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
html, body {{ margin:0; padding:0; background:transparent; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; overflow:hidden; }}
.chat-frame {{ position:relative; height:470px; border-radius:28px; overflow:hidden; background:radial-gradient(circle at top left, rgba(0,212,255,.24), transparent 34%), linear-gradient(180deg, rgba(255,255,255,.12), rgba(255,255,255,.055)); border:1px solid rgba(255,255,255,.16); box-shadow:0 22px 70px rgba(0,0,0,.28); backdrop-filter:blur(20px); }}
.chat-scroll {{ height:100%; overflow-y:auto; padding:18px; box-sizing:border-box; scroll-behavior:auto; opacity:0; transition:opacity .1s ease; }}
.chat-scroll.ready {{ opacity:1; }}
.chat-scroll::-webkit-scrollbar {{ width:8px; }}
.chat-scroll::-webkit-scrollbar-track {{ background:transparent; }}
.chat-scroll::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,.23); border-radius:999px; }}
.msg-row {{ display:flex; margin-bottom:12px; justify-content:flex-start; }}
.msg-row.is-me {{ justify-content:flex-end; }}
.msg-bubble {{ width:fit-content; max-width:74%; padding:12px 14px; border-radius:20px; color:#f6fdff; text-align:left; border:1px solid rgba(255,255,255,.14); box-shadow:0 12px 30px rgba(0,0,0,.18); box-sizing:border-box; }}
.is-me .msg-bubble {{ background:linear-gradient(135deg, rgba(0,212,255,.34), rgba(0,120,255,.30)); border-color:rgba(0,212,255,.28); border-bottom-right-radius:7px; }}
.is-other .msg-bubble {{ background:linear-gradient(135deg, rgba(255,255,255,.13), rgba(255,255,255,.07)); border-bottom-left-radius:7px; }}
.msg-meta {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
.msg-user {{ font-size:13px; font-weight:900; color:#fff; letter-spacing:.01em; }}
.msg-role {{ font-size:10.5px; font-weight:800; padding:2px 7px; border-radius:999px; background:rgba(255,255,255,.13); color:rgba(255,255,255,.82); text-transform:uppercase; }}
.msg-time {{ font-size:11px; color:rgba(255,255,255,.62); }}
.msg-text {{ font-size:14px; line-height:1.46; color:#f8feff; word-break:break-word; text-align:left; }}
.media-card {{ margin-top:10px; border-radius:16px; overflow:hidden; border:1px solid rgba(255,255,255,.12); background:rgba(0,0,0,.20); padding:8px; }}
.voice-title {{ font-size:12px; font-weight:900; color:rgba(255,255,255,.87); margin-bottom:7px; }}
.media-card audio {{ display:block; width:100%; }}
.media-card img {{ display:block; max-width:100%; max-height:280px; object-fit:contain; border-radius:13px; cursor:zoom-in; }}
.media-card video {{ display:block; width:100%; max-height:280px; border-radius:13px; background:rgba(0,0,0,.4); }}
.media-actions {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
.preview-link,.download-link {{ display:inline-flex; align-items:center; justify-content:center; padding:7px 11px; border-radius:999px; background:rgba(0,0,0,.27); color:#fff; font-size:12px; font-weight:900; text-decoration:none; border:1px solid rgba(255,255,255,.15); cursor:pointer; }}
.attachment-chip {{ margin-top:10px; display:inline-flex; max-width:100%; padding:7px 10px; border-radius:999px; background:rgba(0,0,0,.23); color:#fff; font-size:12px; border:1px solid rgba(255,255,255,.12); word-break:break-word; }}
.attachment-note {{ margin-top:7px; color:rgba(255,255,255,.68); font-size:11px; line-height:1.35; }}
.empty-chat {{ height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; color:white; opacity:.86; padding:24px; box-sizing:border-box; }}
.empty-icon {{ font-size:48px; margin-bottom:8px; }} .empty-title {{ font-weight:900; font-size:18px; }} .empty-subtitle {{ margin-top:5px; font-size:13px; color:rgba(255,255,255,.70); max-width:360px; line-height:1.45; }}
.preview-overlay {{ position:fixed; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,.88); z-index:9999; padding:18px; box-sizing:border-box; }}
.preview-overlay.active {{ display:flex; }}
.preview-panel {{ position:relative; width:100%; height:100%; display:flex; align-items:center; justify-content:center; }}
.preview-panel img {{ max-width:96vw; max-height:88vh; border-radius:18px; object-fit:contain; box-shadow:0 24px 80px rgba(0,0,0,.48); }}
.preview-panel video {{ max-width:96vw; max-height:86vh; border-radius:18px; background:black; box-shadow:0 24px 80px rgba(0,0,0,.48); }}
.close-preview {{ position:fixed; top:18px; right:18px; width:44px; height:44px; border-radius:999px; border:1px solid rgba(255,255,255,.18); background:rgba(0,0,0,.62); color:white; font-size:24px; font-weight:900; cursor:pointer; z-index:10000; }}
.jump-btn {{ position:absolute; left:50%; bottom:18px; transform:translateX(-50%); width:46px; height:46px; border-radius:999px; border:1px solid rgba(255,255,255,.25); cursor:pointer; display:none; align-items:center; justify-content:center; color:white; font-size:22px; font-weight:900; background:linear-gradient(135deg,#00d4ff,#0078ff); box-shadow:0 14px 34px rgba(0,0,0,.35),0 0 18px rgba(0,212,255,.38); z-index:90; }}
@media(max-width:700px) {{ .chat-frame{{height:430px;border-radius:22px;}} .msg-bubble{{max-width:88%;}} .chat-scroll{{padding:14px;}} }}
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
const chatScroll=document.getElementById("chatScroll");
const jumpBtn=document.getElementById("jumpBtn");
const overlay=document.getElementById("previewOverlay");
const previewImage=document.getElementById("previewImage");
const previewVideo=document.getElementById("previewVideo");
const previewVideoSource=document.getElementById("previewVideoSource");
function distanceFromBottom(){{ if(!chatScroll) return 0; return chatScroll.scrollHeight-chatScroll.scrollTop-chatScroll.clientHeight; }}
function updateJumpButton(){{ if(!jumpBtn||!chatScroll) return; const dist=distanceFromBottom(); jumpBtn.style.display=dist>180?"flex":"none"; sessionStorage.setItem("dropz_chat_user_scrolled",dist>180?"true":"false"); }}
function scrollToLatest(){{ if(!chatScroll) return; chatScroll.scrollTo({{top:chatScroll.scrollHeight,behavior:"smooth"}}); sessionStorage.setItem("dropz_chat_user_scrolled","false"); setTimeout(updateJumpButton,220); }}
function openImagePreview(src){{ previewVideo.pause(); previewVideo.style.display="none"; previewVideoSource.src=""; previewImage.src=src; previewImage.style.display="block"; overlay.classList.add("active"); }}
function openVideoPreview(src,type){{ previewImage.style.display="none"; previewImage.src=""; previewVideoSource.src=src; previewVideoSource.type=type; previewVideo.load(); previewVideo.style.display="block"; overlay.classList.add("active"); }}
function closePreview(){{ overlay.classList.remove("active"); previewImage.src=""; previewImage.style.display="none"; previewVideo.pause(); previewVideoSource.src=""; previewVideo.load(); previewVideo.style.display="none"; }}
overlay.addEventListener("click",closePreview);
document.addEventListener("keydown",function(event){{ if(event.key==="Escape") closePreview(); }});
if(chatScroll){{ chatScroll.addEventListener("scroll",updateJumpButton); requestAnimationFrame(()=>{{ const userScrolled=sessionStorage.getItem("dropz_chat_user_scrolled")==="true"; if(!userScrolled) chatScroll.scrollTop=chatScroll.scrollHeight; chatScroll.classList.add("ready"); updateJumpButton(); }}); }}
</script>
</body>
</html>
"""


def _inject_chat_css():
    st.markdown(
        """
        <style>
        .dropz-chat-shell {
            padding: 18px;
            border-radius: 28px;
            background: radial-gradient(circle at 10% 10%, rgba(0,212,255,.18), transparent 35%), rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.11);
            box-shadow: 0 24px 80px rgba(0,0,0,.18);
        }
        .dropz-chat-title {
            display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px;
        }
        .dropz-chat-title h2 { margin:0; font-size:28px; line-height:1.1; }
        .live-pill {
            display:inline-flex; align-items:center; gap:7px; padding:7px 11px; border-radius:999px;
            background:rgba(0,255,155,.11); border:1px solid rgba(0,255,155,.20); font-size:13px; font-weight:800;
        }
        .pulse-dot { width:9px; height:9px; border-radius:99px; background:#00ff9b; box-shadow:0 0 18px rgba(0,255,155,.65); }
        div[data-testid="stFileUploader"] section { padding: 8px !important; }
        div[data-testid="stFileUploader"] label { display:none !important; }
        div[data-testid="stTextInput"] input {
            border-radius: 999px !important;
            min-height: 46px !important;
            border: 1px solid rgba(255,255,255,.16) !important;
        }
        .stButton button, .stDownloadButton button, div[data-testid="stFormSubmitButton"] button {
            border-radius: 999px !important;
            min-height: 44px !important;
            font-weight: 900 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_frontend_chat_page(voice_note=None):
    load_theme_css()
    _inject_chat_css()

    st.session_state.setdefault("chat_muted", False)
    st.session_state.setdefault("chat_menu_open", False)
    st.session_state.setdefault("last_voice_note_signature", None)
    st.session_state.setdefault("chat_last_presence_ping", 0.0)
    st.session_state.setdefault("chat_last_seen_message_id", 0)

    # Streamlit-only live update. No websocket server. No realtime client.
    st_autorefresh(interval=REFRESH_MS, key="dropz_streamlit_chat_refresh")

    init_db()
    cleanup_inactive(seconds=35)
    prune_messages()

    user = st.session_state.get("user", {}) or {}
    user_name = str(user.get("name") or user.get("username") or "Guest").strip() or "Guest"
    role = str(user.get("role") or "client").strip() or "client"

    upsert_user(user_name, role)
    now = time.time()
    if now - float(st.session_state.chat_last_presence_ping or 0) >= 5:
        set_user_presence(user_name, role=role, status="active", muted=int(st.session_state.chat_muted))
        st.session_state.chat_last_presence_ping = now

    online_count = get_online_count()
    active_users = get_active_users()
    messages = get_messages(room_id=ROOM_ID, limit=MAX_VISIBLE_MESSAGES)
    latest_id = get_latest_message_id(room_id=ROOM_ID)
    st.session_state.chat_last_seen_message_id = latest_id

    st.markdown('<div class="dropz-chat-shell">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="dropz-chat-title">
            <div>
                <h2>💬 Operations Chat</h2>
                <div style="opacity:.72;font-size:13px;margin-top:4px;">Streamlit live chat · localhost/server synced · no websocket process</div>
            </div>
            <div class="live-pill"><span class="pulse-dot"></span>{online_count} online</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_left, top_right = st.columns([7, 1])
    with top_left:
        if active_users:
            names = ", ".join([str(u.get("name", "User")) for u in active_users[:4]])
            extra = f" +{len(active_users)-4}" if len(active_users) > 4 else ""
            st.caption(f"Active now: {names}{extra}")
        else:
            st.caption("Active now: just you")
    with top_right:
        if st.button("⋯", key="chat_menu_toggle", width="stretch"):
            st.session_state.chat_menu_open = not st.session_state.chat_menu_open
            _rerun()

    if st.session_state.chat_menu_open:
        with st.container(border=True):
            menu_left, menu_right = st.columns([1.1, 2.8])
            with menu_left:
                mute_label = "🔊 Unmute" if st.session_state.chat_muted else "🔇 Mute"
                if st.button(mute_label, key="chat_mute_toggle", width="stretch"):
                    st.session_state.chat_muted = not st.session_state.chat_muted
                    set_user_muted(user_name, int(st.session_state.chat_muted))
                    set_user_presence(user_name, role=role, muted=int(st.session_state.chat_muted))
                    _rerun()
            with menu_right:
                st.caption("Active members")
                for member in active_users[:20]:
                    icon = _status_icon(member)
                    member_name = escape(str(member.get("name", "User")))
                    member_role = escape(str(member.get("role", "client")))
                    st.markdown(f"{icon} **{member_name}** · `{member_role}`")
                if not active_users:
                    st.caption("No active users yet.")

    components.html(_build_chat_html(messages, user_name), height=490, scrolling=False)

    with st.form("dropz_streamlit_chat_form", clear_on_submit=True):
        message = st.text_input("Message", placeholder="Write a message...", label_visibility="collapsed")
        c1, c2, c3 = st.columns([1.15, 1.05, 1.45])
        with c1:
            upload = st.file_uploader(
                "Upload",
                type=["png", "jpg", "jpeg", "webp", "gif", "mp4", "mov", "webm", "wav", "mp3", "m4a", "pdf", "txt", "csv", "docx", "xlsx"],
                label_visibility="collapsed",
            )
        with c2:
            voice_note = st.audio_input("Voice", label_visibility="collapsed", width="stretch")
        with c3:
            send = st.form_submit_button("Send", width="stretch")

        if send:
            text = message.strip() if message else ""
            media_path = None
            media_type = None

            if upload is not None:
                try:
                    media_path, media_type = save_upload(upload, prefix=user_name.replace(" ", "_"))
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")
                    st.stop()

            if voice_note is not None:
                voice_bytes = voice_note.getvalue()
                voice_signature = hashlib.sha256(voice_bytes).hexdigest()
                if st.session_state.last_voice_note_signature != voice_signature:
                    st.session_state.last_voice_note_signature = voice_signature
                    try:
                        media_path, media_type = save_upload(voice_note, prefix=f"voice_{user_name.replace(' ', '_')}")
                    except Exception:
                        from chat_backend.chat_utils import MEDIA_DIR, ensure_dirs
                        ensure_dirs()
                        voice_path = MEDIA_DIR / f"voice_{user_name.replace(' ', '_')}_{int(time.time()*1000)}.wav"
                        voice_path.write_bytes(voice_bytes)
                        media_path, media_type = str(voice_path), "audio/wav"
                    if not text:
                        text = "🎙️ Voice note"

            if text or media_path:
                add_message(user_name, role, text, media_path, media_type, ROOM_ID)
                set_user_presence(user_name, role=role, status="active", muted=int(st.session_state.chat_muted))
                st.toast("Message sent", icon="✅")
                _rerun()
            else:
                st.warning("Type a message or attach a file first.")

    st.markdown("</div>", unsafe_allow_html=True)
