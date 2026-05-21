import sys
import time
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from frontend.style_loader import load_theme_css
from frontend.database import (
    validate_ceo_password,
    validate_token,
    get_all_client_tokens,
    cancel_token,
    delete_user_by_token,
    cancel_all_client_tokens,
    generate_client_token,
    get_active_token_count,
)
from frontend.login_page import render_frontend_login_page
from frontend.dashboard_page import render_frontend_dashboard_page
from frontend.accounts_page import render_frontend_accounts_page
from frontend.tradesmart_page import render_frontend_tradesmart_page
from frontend.chat_page import render_frontend_chat_page
from frontend.tools_page import render_frontend_tools_page
from frontend.settings_client_page import render_settings_client_page
from frontend.settings_ceo_page import render_settings_ceo_page

st.set_page_config(
    page_title="Dropz Universal Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None,
)

def frontend_database():
    pass

frontend_database()
load_theme_css()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user" not in st.session_state:
    st.session_state.user = None
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "dashboard"
if "token_page" not in st.session_state:
    st.session_state.token_page = 1
if "last_chat_refresh" not in st.session_state:
    st.session_state.last_chat_refresh = 0
if "chat_more_menu" not in st.session_state:
    st.session_state.chat_more_menu = False
if "chat_notice" not in st.session_state:
    st.session_state.chat_notice = True
if "chat_mute" not in st.session_state:
    st.session_state.chat_mute = False

def _go(page_name: str):
    st.session_state.selected_page = page_name
    st.rerun()

if not st.session_state.authenticated:
    render_frontend_login_page()
else:
    st.markdown(
        '<div class="brand-card centered-content" style="max-width: 1100px; margin: 0.35rem auto 0.45rem;">',
        unsafe_allow_html=True
    )
    st.markdown('<h1>⚡ Dropz Universal Agent</h1>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Secure client access • AI automation • Trade center</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="top-menu-wrap">', unsafe_allow_html=True)
    menu_cols = st.columns([1, 1, 1, 1, 1, 1, 1])
    menu_labels = ["Dashboard", "Accounts", "TradeSmart", "Chat", "Tools", "Settings", "Logout"]

    for col, label in zip(menu_cols, menu_labels):
        with col:
            if st.button(label, use_container_width=True, key=f"top_{label}"):
                if label == "Logout":
                    st.session_state.authenticated = False
                    st.session_state.user = None
                    st.session_state.selected_page = "dashboard"
                    st.rerun()
                else:
                    _go(label.lower())
    st.markdown('</div>', unsafe_allow_html=True)

    role = st.session_state.user["role"] if st.session_state.user else "client"
    page = st.session_state.selected_page

    if page == "dashboard":
        render_frontend_dashboard_page(role)
    elif page == "accounts":
        render_frontend_accounts_page()
    elif page == "tradesmart":
        render_frontend_tradesmart_page()
    elif page == "chat":
        now = time.time()
        if now - st.session_state.last_chat_refresh > 30:
            st.session_state.last_chat_refresh = now
        render_frontend_chat_page()
    elif page == "tools":
        render_frontend_tools_page()
    elif page == "settings":
        if role == "ceo":
            render_settings_ceo_page(role)
        else:
            render_settings_client_page(role)