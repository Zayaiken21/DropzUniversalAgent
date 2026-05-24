# =========================================
# chat_page.py
# PRODUCTION READY CRO CHAT
# =========================================

from pathlib import Path
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components


from frontend.realtime_client import RealtimeClient

from chat_backend.chat_db import (
    init_db,
    upsert_user,
    set_user_presence,
    mark_user_offline,
    add_message,
    get_messages,
    prune_messages,
    cleanup_inactive,
    get_active_users,
    get_online_count,
)

# =========================================
# FILE SAVE
# =========================================

def _save_upload(upload):

    media_dir = Path("chat_backend/uploads")

    media_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = media_dir / upload.name

    with open(file_path, "wb") as f:
        f.write(upload.getbuffer())

    return str(file_path), upload.type


# =========================================
# STATUS DOT
# =========================================

def _status_dot(status):

    if status == "sharing":
        return "📞"

    if status == "idle":
        return "🟡"

    return "🟢"


# =========================================
# MESSAGE RENDER
# =========================================

def _render_message(msg, idx, current_user):

    is_me = msg["user_name"] == current_user

    row_class = (
        "message-row me-row"
        if is_me
        else "message-row"
    )

    bubble_class = (
        "chat-bubble my-bubble"
        if is_me
        else "chat-bubble"
    )

    st.markdown(
        f"""
        <div class="{row_class}">

            <div class="{bubble_class}">

                <div class="message-top">

                    <div class="message-user">
                        {msg["user_name"]}
                    </div>

                    <div class="message-time">
                        {msg["created_at"]}
                    </div>

                </div>

                <div class="message-role">
                    {msg["role"]}
                </div>

                <div class="message-content">
                    {msg.get("message", "")}
                </div>
        """,
        unsafe_allow_html=True
    )

    # =========================================
    # MEDIA
    # =========================================

    if msg.get("media_path"):

        mt = (msg.get("media_type") or "").lower()

        media_path = msg["media_path"]

        st.markdown(
            '<div class="media-wrap">',
            unsafe_allow_html=True
        )

        if mt.startswith("image/"):

            st.image(
                media_path,
                use_container_width=True
            )

        elif mt.startswith("video/"):

            st.video(media_path)

        else:

            with open(media_path, "rb") as f:

                st.download_button(
                    "Download Attachment",
                    data=f.read(),
                    file_name=Path(media_path).name,
                    use_container_width=True,
                    key=f"download_{msg['id']}_{idx}"
                )

        st.markdown(
            "</div>",
            unsafe_allow_html=True
        )

    st.markdown(
        """
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================
# MAIN CHAT PAGE
# =========================================

def render_frontend_chat_page():

    

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

    # =========================================
    # SESSION
    # =========================================

    defaults = {
        "chat_more_menu": False,
        "chat_mute": False,
        "in_call": False,
        "chat_last_ping": 0.0,
    }

    for k, v in defaults.items():

        if k not in st.session_state:
            st.session_state[k] = v

    # =========================================
    # PRESENCE
    # =========================================

    upsert_user(user_name, role)

    now = datetime.now().timestamp()

    if now - st.session_state.chat_last_ping >= 5:

        status = (
            "sharing"
            if st.session_state.in_call
            else "active"
        )

        set_user_presence(
            user_name,
            1,
            status,
            muted=int(st.session_state.chat_mute),
            in_call=int(st.session_state.in_call)
        )

        rt.send_presence(
            room_id,
            user_id,
            user_name,
            muted=st.session_state.chat_mute,
            in_call=st.session_state.in_call
        )

        st.session_state.chat_last_ping = now

    # =========================================
    # DATA
    # =========================================

    active_users = get_active_users()

    online_count = get_online_count()

    messages = get_messages(
        room_id=room_id,
        limit=300
    )

    # =========================================
    # MAIN SHELL
    # =========================================

    st.markdown(
        """
        <div class="cro-chat-shell">
        """,
        unsafe_allow_html=True
    )

    # =========================================
    # HEADER
    # =========================================

    left, middle, right = st.columns([5, 1.2, 0.6])

    with left:

        st.markdown(
            f"""
            <div class="chat-header-card">

                <div class="chat-brand">
                    💬 Operations Chat
                </div>

                <div class="chat-sub">
                    Secure realtime communication & collaboration
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    with middle:

        st.markdown(
            f"""
            <div class="online-card">

                <div class="online-dot"></div>

                <div class="online-text">
                    {online_count} Online
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    with right:

        if st.button(
            "⋯",
            key="chat_menu_button",
            use_container_width=True
        ):

            st.session_state.chat_more_menu = (
                not st.session_state.chat_more_menu
            )

            st.rerun()

    # =========================================
    # MENU
    # =========================================

    if st.session_state.chat_more_menu:

        st.markdown(
            """
            <div class="chat-menu-card">
            """,
            unsafe_allow_html=True
        )

        m1, m2 = st.columns(2)

        with m1:

            if st.button(
                "🔕 Muted"
                if st.session_state.chat_mute
                else "🔔 Notifications",
                use_container_width=True,
                key="mute_toggle"
            ):

                st.session_state.chat_mute = (
                    not st.session_state.chat_mute
                )

                st.rerun()

        with m2:

            if st.button(
                "📞 Leave Call"
                if st.session_state.in_call
                else "📞 Join Call",
                use_container_width=True,
                key="call_toggle"
            ):

                st.session_state.in_call = (
                    not st.session_state.in_call
                )

                st.rerun()

        st.markdown(
            """
            <div class="active-title">
                Active Team
            </div>
            """,
            unsafe_allow_html=True
        )

        for member in active_users:

            status = member.get(
                "status",
                "active"
            )

            st.markdown(
                f"""
                <div class="active-user">

                    <div class="active-left">
                        {_status_dot(status)}
                        {member['name']}
                    </div>

                    <div class="active-right">
                        {status}
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            "</div>",
            unsafe_allow_html=True
        )

    # =========================================
    # CHAT CANVAS
    # =========================================

    st.markdown(
        """
        <div class="chat-canvas">

            <div
                class="chat-scroll-area"
                id="chat_scroll_area"
            >
        """,
        unsafe_allow_html=True
    )

    for i, msg in enumerate(messages[-140:]):

        _render_message(
            msg,
            i,
            user_name
        )

    st.markdown(
        """
            </div>

            <button
                id="scroll_bottom_btn"
                class="scroll-bottom-btn"
                onclick="scrollChatBottom()"
            >
                ↓
            </button>

        </div>
        """,
        unsafe_allow_html=True
    )

    # =========================================
    # COMPOSER
    # =========================================

    st.markdown(
        """
        <div class="composer-shell">
        """,
        unsafe_allow_html=True
    )

    with st.form(
        "chat_form",
        clear_on_submit=True
    ):

        message = st.text_area(
            "Message",
            placeholder="Write a message...",
            label_visibility="collapsed",
            height=78
        )

        c1, c2, c3 = st.columns([0.8, 0.8, 4])

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
                    "txt"
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
                "Send Message",
                use_container_width=True
            )

        # SEND

        if send:

            media_path = None
            media_type = None

            msg_text = (
                message.strip()
                if message
                else ""
            )

            if upload is not None:

                media_path, media_type = (
                    _save_upload(upload)
                )

            if msg_text or media_path:

                add_message(
                    user_name,
                    role,
                    msg_text,
                    media_path,
                    media_type,
                    room_id
                )

                rt.send_chat(
                    room_id,
                    user_id,
                    user_name,
                    role,
                    msg_text,
                    media_path,
                    media_type
                )

                st.rerun()

        if voice:

            st.info(
                "Voice connected through realtime backend."
            )

    st.markdown(
        "</div></div>",
        unsafe_allow_html=True
    )

    # =========================================
    # SCROLL SCRIPT
    # =========================================

    components.html(
        """
        <script>

        const parentDoc = window.parent.document;

        setTimeout(() => {

            const scrollArea =
                parentDoc.querySelector(
                    '#chat_scroll_area'
                );

            const btn =
                parentDoc.querySelector(
                    '#scroll_bottom_btn'
                );

            if (!scrollArea || !btn) return;

            function updateButton() {

                const nearBottom =
                    scrollArea.scrollHeight
                    - scrollArea.scrollTop
                    - scrollArea.clientHeight
                    < 180;

                if (nearBottom) {
                    btn.style.opacity = '0';
                    btn.style.pointerEvents = 'none';
                } else {
                    btn.style.opacity = '1';
                    btn.style.pointerEvents = 'auto';
                }
            }

            window.scrollChatBottom = function() {

                scrollArea.scrollTo({
                    top: scrollArea.scrollHeight,
                    behavior: 'smooth'
                });

            }

            scrollArea.addEventListener(
                'scroll',
                updateButton
            );

            updateButton();

            scrollArea.scrollTop =
                scrollArea.scrollHeight;

        }, 300);

        </script>
        """,
        height=0
    )