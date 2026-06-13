"""
chat_page.py — TradeSmart Pro Chat (stable UI + production fixes)
==================================================================
Keeps the original dark-glass chat UI, fixes Streamlit uploader duplicate wording,
adds Enter/Return send behavior through a single-line message input, removes the
mute button, adds CEO-only clear chat inside the 3-dot menu, and reduces refresh
flicker with slower stable polling.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import time
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh


def _ensure_package(pkg_name: str, pkg_dir: Path) -> None:
    if pkg_name in sys.modules:
        return
    if not pkg_dir.is_dir():
        raise ImportError(f"Package directory not found: {pkg_dir}")
    parent = str(pkg_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    import importlib
    importlib.import_module(pkg_name)


def _import_backend() -> None:
    here = Path(__file__).resolve().parent
    root = here.parent
    backend = root / "chat_backend"
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    here_str = str(here)
    if here_str not in sys.path:
        sys.path.insert(0, here_str)
    _ensure_package("chat_backend", backend)


try:
    _import_backend()
    from chat_backend.chat_db import (
        init_db,
        upsert_user,
        set_user_presence,
        add_message,
        get_messages,
        get_latest_message_id,
        prune_messages,
        cleanup_inactive,
        get_active_users,
        get_online_count,
        get_pending_agent_messages,
        mark_agent_replied,
        has_agent_replied,
        clear_chat_messages,
    )
    from chat_backend.chat_media import save_upload
    from chat_backend.chat_time import to_est_label
    from chat_agent import call_agent, AGENT_USER, AGENT_ROLE
except Exception as _imp_err:
    st.error(f"Chat import error: {_imp_err}")
    raise

try:
    from frontend.style_loader import load_theme_css
except Exception:
    def load_theme_css():
        return None


MAX_IMAGE_PREVIEW_MB = 25
MAX_VIDEO_PREVIEW_MB = 18
MAX_VISIBLE_MESSAGES = 90
REFRESH_MS = 12000          # slower polling prevents flicker/seizure-like refresh
PRESENCE_INTERVAL_S = 18    # do not write presence every rerun
ROOM_ID = "main"

_AVATAR_COLORS = [
    "#1e6fff", "#00c49a", "#ff6b35", "#9b5cff",
    "#ff3d8a", "#00bcd4", "#f4c542", "#4caf50",
]


def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _is_ceo_role(role: str) -> bool:
    return str(role or "").strip().lower() in {"ceo", "owner", "admin", "superadmin"}


def _file_size_mb(path) -> float:
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def _avatar_color(name: str) -> str:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_AVATAR_COLORS)
    return _AVATAR_COLORS[idx]


def _avatar_initials(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def _status_icon(member: dict) -> str:
    if member.get("status") == "idle":
        return "🟡"
    return "🟢"


def _role_badge_color(role: str) -> str:
    return {
        "ceo": "#ff6b35",
        "owner": "#ff6b35",
        "admin": "#ff6b35",
        "agent": "#9b5cff",
        "analyst": "#00c49a",
        "client": "#1e6fff",
    }.get(str(role).lower(), "#576b99")


def _media_html(msg: dict) -> str:
    media_path = msg.get("media_path")
    media_type = (msg.get("media_type") or "").lower()
    if not media_path:
        return ""

    path = Path(media_path)
    filename = escape(path.name)

    if not path.exists():
        return (
            f'<div class="attachment-chip">📎 {filename}</div>'
            f'<div class="attachment-note">File no longer available on this server.</div>'
        )

    size_mb = _file_size_mb(path)
    if media_type.startswith("image/") and size_mb > MAX_IMAGE_PREVIEW_MB:
        return (
            f'<div class="attachment-chip">🖼️ {filename} · {size_mb:.1f} MB</div>'
            f'<div class="attachment-note">Preview disabled for large image. File saved.</div>'
        )
    if media_type.startswith("video/") and size_mb > MAX_VIDEO_PREVIEW_MB:
        return (
            f'<div class="attachment-chip">🎬 {filename} · {size_mb:.1f} MB</div>'
            f'<div class="attachment-note">Preview disabled — file saved to server.</div>'
        )

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return f'<div class="attachment-chip">📎 {filename}</div><div class="attachment-note">Preview unavailable.</div>'

    if media_type.startswith("audio/"):
        return (
            f'<div class="media-card voice-card">'
            f'<div class="voice-title">🎙️ Voice note</div>'
            f'<audio controls preload="metadata">'
            f'<source src="data:{media_type};base64,{encoded}" type="{media_type}"></audio>'
            f'</div>'
        )
    if media_type.startswith("image/"):
        return (
            f'<div class="media-card">'
            f'<img class="chat-image" src="data:{media_type};base64,{encoded}" alt="{filename}" '
            f'onclick="openImagePreview(this.src)" />'
            f'<div class="media-actions">'
            f'<button class="preview-link" onclick="openImagePreview(this.closest(\'.media-card\').querySelector(\'img\').src)">Expand</button>'
            f'<a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download</a>'
            f'</div></div>'
        )
    if media_type.startswith("video/"):
        return (
            f'<div class="media-card">'
            f'<video class="chat-video" controls playsinline preload="metadata">'
            f'<source src="data:{media_type};base64,{encoded}" type="{media_type}"></video>'
            f'<div class="media-actions">'
            f'<button class="preview-link" onclick="openVideoPreview(\'data:{media_type};base64,{encoded}\',\'{media_type}\')">Expand</button>'
            f'<a class="download-link" download="{filename}" href="data:{media_type};base64,{encoded}">Download</a>'
            f'</div></div>'
        )
    return f"<div class='attachment-chip'>📎 {filename}</div>"


def _build_chat_html(messages: list[dict], current_user: str) -> str:
    bubbles = []
    for msg in messages[-MAX_VISIBLE_MESSAGES:]:
        is_me = msg.get("user_name") == current_user
        is_agent = msg.get("user_name") == AGENT_USER
        user_name = str(msg.get("user_name") or "User")
        role = str(msg.get("role") or "client")
        created_at = to_est_label(str(msg.get("created_at") or ""))
        text_raw = str(msg.get("message") or "")
        text = escape(text_raw).replace("\n", "<br>")
        media = _media_html(msg)

        side_cls = "is-me" if is_me else ("is-agent" if is_agent else "is-other")
        av_color = "#9b5cff" if is_agent else _avatar_color(user_name)
        av_initials = "AI" if is_agent else _avatar_initials(user_name)
        badge_color = _role_badge_color(role)
        display_name = escape(user_name)
        role_label = escape(role)

        avatar_html = f'<div class="msg-avatar" style="background:{av_color}">{escape(av_initials)}</div>'
        meta_html = (
            f'<div class="msg-meta">'
            f'<span class="msg-user">{display_name}</span>'
            f'<span class="msg-badge" style="background:{badge_color}22;color:{badge_color};border:1px solid {badge_color}44">{role_label}</span>'
            f'<span class="msg-time">{escape(created_at)}</span>'
            f'</div>'
        )
        text_block = f'<div class="msg-text">{text}</div>' if text else ""
        bubbles.append(
            f'<div class="msg-row {side_cls}">'
            f'{"" if is_me else avatar_html}'
            f'<div class="msg-bubble">{meta_html}{text_block}{media}</div>'
            f'{avatar_html if is_me else ""}'
            f'</div>'
        )

    if not bubbles:
        body = (
            '<div class="empty-chat">'
            '<div class="empty-icon">💬</div>'
            '<div class="empty-title">No messages yet</div>'
            '<div class="empty-sub">Type a message below — all connected users will see it live.</div>'
            '<div class="agent-hint">Tip: type <b>@Agent</b> anywhere in your message to ask the AI assistant.</div>'
            '</div>'
        )
    else:
        body = "\n".join(bubbles)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:transparent;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;overflow:hidden}}
.chat-frame{{position:relative;height:500px;border-radius:26px;overflow:hidden;background:radial-gradient(ellipse at 10% 5%,rgba(0,212,255,.16),transparent 30%),radial-gradient(ellipse at 90% 90%,rgba(100,60,255,.12),transparent 28%),linear-gradient(180deg,rgba(10,22,42,.95),rgba(4,12,26,.98));border:1px solid rgba(0,212,255,.16);box-shadow:0 24px 72px rgba(0,0,0,.40),inset 0 1px 0 rgba(255,255,255,.06)}}
.chat-scroll{{height:100%;overflow-y:auto;padding:20px 16px;scroll-behavior:auto;opacity:1}}
.chat-scroll::-webkit-scrollbar{{width:5px}}
.chat-scroll::-webkit-scrollbar-track{{background:transparent}}
.chat-scroll::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.22);border-radius:999px}}
.msg-row{{display:flex;align-items:flex-end;gap:8px;margin-bottom:14px}}
.msg-row.is-me{{flex-direction:row-reverse}}
.msg-row.is-agent{{flex-direction:row}}
.msg-avatar{{width:32px;height:32px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:.60rem;font-weight:900;letter-spacing:.03em;color:#fff;flex-shrink:0;box-shadow:0 4px 14px rgba(0,0,0,.28)}}
.msg-bubble{{max-width:72%;padding:11px 14px;border-radius:20px;border:1px solid rgba(255,255,255,.10);box-shadow:0 8px 26px rgba(0,0,0,.20);word-break:break-word}}
.is-me .msg-bubble{{background:linear-gradient(135deg,rgba(0,180,255,.30),rgba(0,90,210,.28));border-color:rgba(0,212,255,.24);border-bottom-right-radius:6px}}
.is-other .msg-bubble{{background:linear-gradient(135deg,rgba(255,255,255,.10),rgba(255,255,255,.06));border-bottom-left-radius:6px}}
.is-agent .msg-bubble{{background:linear-gradient(135deg,rgba(140,80,255,.22),rgba(80,40,200,.20));border-color:rgba(155,92,255,.28);border-bottom-left-radius:6px}}
.msg-meta{{display:flex;align-items:center;gap:6px;margin-bottom:5px;flex-wrap:wrap}}
.msg-user{{font-size:.68rem;font-weight:800;color:rgba(200,230,255,.92);letter-spacing:.02em}}
.msg-badge{{font-size:.56rem;font-weight:700;padding:1px 7px;border-radius:999px;letter-spacing:.06em;text-transform:uppercase}}
.msg-time{{font-size:.60rem;color:rgba(140,180,220,.52);margin-left:auto}}
.msg-text{{font-size:.875rem;color:rgba(235,248,255,.94);line-height:1.58;font-weight:400}}
.media-card{{margin-top:8px;border-radius:14px;overflow:hidden;background:rgba(4,18,36,.68);border:1px solid rgba(0,212,255,.14)}}
.voice-card{{padding:10px;background:rgba(0,212,255,.10)}}
.voice-title{{font-size:.70rem;font-weight:700;color:rgba(0,212,255,.88);margin-bottom:6px}}
.chat-image{{width:100%;max-height:260px;object-fit:cover;display:block;cursor:pointer;border-radius:12px}}
.chat-video{{width:100%;max-height:220px;display:block;border-radius:12px}}
.media-actions{{display:flex;gap:8px;padding:8px 10px 10px}}
.preview-link,.download-link{{font-size:.70rem;font-weight:700;cursor:pointer;border-radius:999px;padding:5px 13px;border:1px solid rgba(0,212,255,.28);background:rgba(0,212,255,.10);color:rgba(0,212,255,.94);text-decoration:none;transition:background .15s ease}}
.preview-link:hover,.download-link:hover{{background:rgba(0,212,255,.22)}}
.attachment-chip{{display:inline-block;font-size:.74rem;padding:5px 11px;background:rgba(0,212,255,.10);border:1px solid rgba(0,212,255,.22);border-radius:999px;color:rgba(180,220,255,.82);margin-top:7px}}
.attachment-note{{font-size:.66rem;color:rgba(140,180,220,.54);margin-top:4px}}
.empty-chat{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:85%;gap:10px;text-align:center;padding:20px}}
.empty-icon{{font-size:2.4rem;opacity:.55}}
.empty-title{{font-size:1rem;font-weight:700;color:rgba(180,210,255,.72)}}
.empty-sub{{font-size:.78rem;color:rgba(120,160,210,.50);max-width:300px;line-height:1.5}}
.agent-hint{{font-size:.74rem;color:rgba(155,92,255,.72);margin-top:6px;padding:6px 14px;border-radius:999px;border:1px solid rgba(155,92,255,.22);background:rgba(155,92,255,.08)}}
.jump-btn{{position:absolute;bottom:14px;right:14px;background:rgba(0,212,255,.88);color:#fff;border:none;border-radius:999px;padding:7px 14px;font-size:.72rem;font-weight:800;cursor:pointer;box-shadow:0 6px 20px rgba(0,140,200,.30);display:none;z-index:10}}
.overlay{{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;z-index:999;cursor:pointer}}
.overlay.active{{display:flex}}
.overlay img,.overlay video{{max-width:92vw;max-height:88vh;border-radius:16px;object-fit:contain;cursor:default;box-shadow:0 0 80px rgba(0,212,255,.18)}}
</style>
</head>
<body>
<div class="overlay" id="overlay">
  <img id="previewImage" style="display:none" alt="preview"/>
  <video id="previewVideo" style="display:none" controls playsinline><source id="previewVideoSource" src="" type=""/></video>
</div>
<div class="chat-frame">
  <div class="chat-scroll" id="chatScroll">{body}</div>
  <button class="jump-btn" id="jumpBtn" onclick="scrollToBottom()">↓ New messages</button>
</div>
<script>
const chatScroll=document.getElementById("chatScroll");
const jumpBtn=document.getElementById("jumpBtn");
const overlay=document.getElementById("overlay");
const previewImage=document.getElementById("previewImage");
const previewVideo=document.getElementById("previewVideo");
const previewVideoSource=document.getElementById("previewVideoSource");
function isAtBottom(){{return chatScroll.scrollHeight-chatScroll.scrollTop-chatScroll.clientHeight<80;}}
function scrollToBottom(){{chatScroll.scrollTop=chatScroll.scrollHeight;jumpBtn.style.display="none";}}
chatScroll.addEventListener("scroll",()=>{{jumpBtn.style.display=(!isAtBottom())?"block":"none";}});
requestAnimationFrame(()=>{{scrollToBottom();}});
function openImagePreview(src){{previewVideo.style.display="none";previewImage.src=src;previewImage.style.display="block";overlay.classList.add("active");}}
function openVideoPreview(src,type){{previewImage.style.display="none";previewVideoSource.src=src;previewVideoSource.type=type;previewVideo.load();previewVideo.style.display="block";overlay.classList.add("active");}}
function closePreview(){{overlay.classList.remove("active");previewImage.src="";previewVideo.pause();previewVideoSource.src="";previewVideo.load();previewImage.style.display="none";previewVideo.style.display="none";}}
overlay.addEventListener("click",closePreview);
document.addEventListener("keydown",e=>{{if(e.key==="Escape")closePreview();}});
</script>
</body>
</html>"""


def _inject_shell_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif !important; }

    .ts-chat-shell {
        padding: 0;
        border-radius: 28px;
        background: radial-gradient(ellipse at 12% 8%, rgba(0,212,255,.10), transparent 32%),
                    rgba(8, 18, 36, 0.60);
        border: 1px solid rgba(0,212,255,.12);
        box-shadow: 0 28px 88px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.05);
        overflow: hidden;
    }
    .ts-chat-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 12px;
        border-bottom: 1px solid rgba(0,212,255,.10);
        background: rgba(4, 14, 30, 0.70);
    }
    .ts-chat-header h2 { margin: 0; font-size: 1.15rem; font-weight: 800; color: #e8f4ff; letter-spacing: .02em; }
    .ts-chat-sub { font-size: .68rem; color: rgba(120,170,220,.56); margin-top: 3px; font-weight: 500; }
    .live-pill { display: inline-flex; align-items: center; gap: 7px; padding: 6px 12px; border-radius: 999px; background: rgba(0,230,118,.10); border: 1px solid rgba(0,230,118,.22); font-size: .72rem; font-weight: 800; color: rgba(0,230,118,.92); letter-spacing: .06em; white-space: nowrap; }
    .pulse-dot { width: 8px; height: 8px; border-radius: 999px; background: #00e676; }
    .agent-pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px; background: rgba(155,92,255,.10); border: 1px solid rgba(155,92,255,.24); font-size: .64rem; font-weight: 700; color: rgba(180,140,255,.82); margin-top: 4px; }
    .ts-member { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid rgba(0,212,255,.07); font-size: .76rem; color: rgba(180,210,255,.80); }
    .ts-member:last-child { border-bottom: none; }
    .ts-member-av { width: 26px; height: 26px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: .56rem; font-weight: 900; color: #fff; flex-shrink: 0; }
    .ts-member-name { font-weight: 700; color: rgba(220,240,255,.88); }
    .ts-member-role { font-size: .58rem; font-weight: 700; padding: 1px 6px; border-radius: 999px; margin-left: 4px; background: rgba(30,111,255,.16); color: rgba(100,170,255,.82); border: 1px solid rgba(30,111,255,.22); }
    .clear-chat-danger button { background: rgba(255,80,80,.18) !important; border: 1px solid rgba(255,80,80,.35) !important; color: #ffd4d4 !important; }

    /* Upload duplicate-wording fix. Keep the button, hide labels/instruction text. */
    div[data-testid="stFileUploader"] label,
    div[data-testid="stFileUploader"] small,
    div[data-testid="stFileUploader"] [data-testid="stMarkdownContainer"],
    div[data-testid="stFileUploader"] section > div:first-child:not(:has(button)) {
        display: none !important;
    }
    div[data-testid="stFileUploader"] section {
        padding: 0 !important;
        border: 0 !important;
        background: transparent !important;
    }
    div[data-testid="stFileUploader"] button {
        width: 100% !important;
        border-radius: 14px !important;
        min-height: 42px !important;
    }
    div[data-testid="stTextInput"] input {
        min-height: 52px !important;
        border-radius: 16px !important;
        font-weight: 600 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _process_agent_messages():
    pending = get_pending_agent_messages(room_id=ROOM_ID)
    for row in pending:
        msg_id = row["id"]
        user_name = row["user_name"]
        message = row["message"] or ""
        if has_agent_replied(msg_id):
            continue
        mark_agent_replied(msg_id)
        reply = call_agent(user_name, message)
        add_message(AGENT_USER, AGENT_ROLE, reply, room_id=ROOM_ID)


def render_frontend_chat_page(voice_note=None):
    load_theme_css()
    _inject_shell_css()

    st.session_state.setdefault("chat_menu_open", False)
    st.session_state.setdefault("last_voice_note_sig", None)
    st.session_state.setdefault("chat_last_presence_ping", 0.0)
    st.session_state.setdefault("chat_html_hash", "")
    st.session_state.setdefault("chat_clear_confirm", False)

    # Stable live polling. This is intentionally slow to avoid flicker/seizure-like reruns.
    st_autorefresh(interval=REFRESH_MS, key="ts_chat_stable_refresh")

    init_db()
    cleanup_inactive(seconds=60)
    prune_messages()

    user = st.session_state.get("user", {}) or {}
    user_name = str(user.get("name") or user.get("username") or "Guest").strip() or "Guest"
    role = str(user.get("role") or "client").strip() or "client"
    is_ceo = _is_ceo_role(role)

    upsert_user(user_name, role)
    now_ts = time.time()
    if now_ts - float(st.session_state.chat_last_presence_ping or 0) >= PRESENCE_INTERVAL_S:
        set_user_presence(user_name, role=role, status="active", muted=0)
        st.session_state.chat_last_presence_ping = now_ts

    _process_agent_messages()

    online_count = get_online_count()
    active_users = get_active_users()
    messages = get_messages(room_id=ROOM_ID, limit=MAX_VISIBLE_MESSAGES)

    st.markdown('<div class="ts-chat-shell">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ts-chat-header">'
        f'<div><h2>💬 Operations Chat</h2>'
        f'<div class="ts-chat-sub">Live · SQLite-backed · stable polling</div>'
        f'<div class="agent-pill">🤖 @Agent available — mention it to ask the AI</div></div>'
        f'<div class="live-pill"><span class="pulse-dot"></span>{online_count} online</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    top_l, top_r = st.columns([8, 1])
    with top_l:
        names_preview = [str(u.get("name") or "User") for u in active_users[:5]]
        extra = f" +{len(active_users)-5}" if len(active_users) > 5 else ""
        label = (", ".join(names_preview) + extra) if names_preview else "just you"
        st.caption(f"Active: {label}")
    with top_r:
        if st.button("⋯", key="chat_menu_toggle"):
            st.session_state.chat_menu_open = not st.session_state.chat_menu_open
            _rerun()

    if st.session_state.chat_menu_open:
        with st.container(border=True):
            st.caption("Members online")
            members_html = ""
            for m in active_users[:20]:
                mname = str(m.get("name") or "User")
                mrole = str(m.get("role") or "client")
                av_c = _avatar_color(mname)
                av_i = _avatar_initials(mname)
                icon = _status_icon(m)
                members_html += (
                    f'<div class="ts-member">'
                    f'<div class="ts-member-av" style="background:{av_c}">{escape(av_i)}</div>'
                    f'<span class="ts-member-name">{escape(mname)}</span>'
                    f'<span class="ts-member-role">{escape(mrole)}</span>'
                    f'<span style="margin-left:auto">{icon}</span>'
                    f'</div>'
                )
            if not members_html:
                members_html = '<div class="ts-member" style="color:rgba(120,160,200,.5)">No active users yet.</div>'
            st.markdown(members_html, unsafe_allow_html=True)

            if is_ceo:
                st.divider()
                if not st.session_state.chat_clear_confirm:
                    st.markdown('<div class="clear-chat-danger">', unsafe_allow_html=True)
                    if st.button("Clear full chat", key="chat_clear_start", use_container_width=True):
                        st.session_state.chat_clear_confirm = True
                        _rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.warning("This will permanently clear all chat messages in this room.")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown('<div class="clear-chat-danger">', unsafe_allow_html=True)
                        if st.button("Yes, clear chat", key="chat_clear_confirm_yes", use_container_width=True):
                            clear_chat_messages(room_id=ROOM_ID)
                            st.session_state.chat_clear_confirm = False
                            st.session_state.chat_menu_open = False
                            _rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                    with c2:
                        if st.button("Cancel", key="chat_clear_cancel", use_container_width=True):
                            st.session_state.chat_clear_confirm = False
                            _rerun()

    chat_html = _build_chat_html(messages, user_name)
    components.html(chat_html, height=520, scrolling=False)

    # Single-line input allows Enter/Return to submit on laptop and phone.
    with st.form("ts_chat_form", clear_on_submit=True):
        message = st.text_input(
            "Message",
            placeholder="Type a message… or use @Agent to ask the AI assistant",
            label_visibility="collapsed",
            key="ts_chat_message_input",
        )
        fc1, fc2, fc3 = st.columns([1.15, 1.05, 1.45])
        with fc1:
            upload = st.file_uploader(
                "Upload file",
                type=["png", "jpg", "jpeg", "webp", "gif", "mp4", "mov", "webm",
                      "wav", "mp3", "m4a", "pdf", "txt", "csv", "docx", "xlsx"],
                label_visibility="collapsed",
                key="ts_chat_upload",
            )
        with fc2:
            voice_rec = st.audio_input("Voice", label_visibility="collapsed", key="ts_chat_voice")
        with fc3:
            send = st.form_submit_button("Send ↑", use_container_width=True)

        if send:
            text = (message or "").strip()
            media_path = None
            media_type = None

            if upload is not None:
                try:
                    media_path, media_type = save_upload(upload, prefix=user_name.replace(" ", "_"))
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")
                    st.stop()

            if voice_rec is not None:
                vbytes = voice_rec.getvalue()
                vsig = hashlib.sha256(vbytes).hexdigest()
                if st.session_state.last_voice_note_sig != vsig:
                    st.session_state.last_voice_note_sig = vsig
                    try:
                        media_path, media_type = save_upload(voice_rec, prefix=f"voice_{user_name.replace(' ', '_')}")
                    except Exception:
                        from chat_backend.chat_utils import MEDIA_DIR, ensure_dirs
                        ensure_dirs()
                        vp = MEDIA_DIR / f"voice_{user_name.replace(' ', '_')}_{int(time.time()*1000)}.wav"
                        vp.write_bytes(vbytes)
                        media_path, media_type = str(vp), "audio/wav"
                    if not text:
                        text = "🎙️ Voice note"

            if text or media_path:
                add_message(user_name, role, text, media_path, media_type, ROOM_ID)
                set_user_presence(user_name, role=role, status="active", muted=0)
                _rerun()
            else:
                st.warning("Type a message or attach a file first.")

    st.markdown("</div>", unsafe_allow_html=True)
