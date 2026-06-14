import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Local PyCharm .env support
load_dotenv(ROOT_DIR / ".env")


def get_secret(name: str, default: str = "") -> str:
    """
    Streamlit Cloud reads st.secrets.
    Local PyCharm reads .env.
    """
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.getenv(name, default)


CEO_SECRET_PHRASE = get_secret("CEO_SECRET_PHRASE")
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
DROPZ_UPDATE_MANIFEST_URL = get_secret("DROPZ_UPDATE_MANIFEST_URL")


from frontend.style_loader import load_theme_css
from frontend.login_page import render_frontend_login_page
from frontend.dashboard_page import render_frontend_dashboard_page
from frontend.education_page import render_frontend_education_page
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

load_theme_css()

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stApp {
        font-size: clamp(13px, 1.6vw, 18px) !important;
    }
    html, body, [class*="css"] {
        font-size: clamp(13px, 1.6vw, 18px) !important;
    }
    .block-container {
        padding-top: 0.35rem !important;
        padding-bottom: 0.6rem !important;
        max-width: 100% !important;
    }

    /* Stop global font-size clamp from inflating menu button labels */
    .st-key-top_menu_area div[data-testid="stButton"] button,
    .st-key-top_menu_area div[data-testid="stButton"] button p {
        font-size: 12px !important;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
        }
        /* Stack columns on mobile for all blocks EXCEPT the top nav menu */
        [data-testid="stHorizontalBlock"]:not(
            .st-key-top_menu_area [data-testid="stHorizontalBlock"]
        ) {
            flex-direction: column !important;
        }
        [data-testid="stHorizontalBlock"]:not(
            .st-key-top_menu_area [data-testid="stHorizontalBlock"]
        ) > [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }

        /* Keep menu as 7-column grid on mobile — never stacked */
        .st-key-top_menu_area div[data-testid="stHorizontalBlock"] {
            display: grid !important;
            grid-template-columns: repeat(7, minmax(0, 1fr)) !important;
            flex-direction: unset !important;
        }
        .st-key-top_menu_area [data-testid="column"] {
            width: 100% !important;
            flex: unset !important;
        }

        /* Mobile menu button font */
        .st-key-top_menu_area div[data-testid="stButton"] button,
        .st-key-top_menu_area div[data-testid="stButton"] button p {
            font-size: 9.8px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _inject_global_enter_submit():
    """
    App-wide Enter/Return support:
    - Inside Streamlit forms, Enter clicks that form's submit button.
    - Outside forms, Enter clicks the nearest visible button in the same input block when possible.
    - Textareas keep normal multiline behavior unless Ctrl/Cmd+Enter is used.
    """
    st.markdown(
        """
        <script>
        (function () {
            if (window.__dropzEnterSubmitInstalled) return;
            window.__dropzEnterSubmitInstalled = true;

            function isVisible(el) {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            }

            function clickFirstVisibleButton(root) {
                if (!root) return false;
                const buttons = Array.from(root.querySelectorAll('button'));
                for (const btn of buttons) {
                    if (!btn.disabled && isVisible(btn)) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }

            function findInputBlock(el) {
                return el.closest('[data-testid="stForm"]')
                    || el.closest('[data-testid="stVerticalBlock"]')
                    || el.closest('[data-testid="stHorizontalBlock"]')
                    || document.body;
            }

            document.addEventListener('keydown', function (event) {
                const target = event.target;
                if (!target) return;

                const tag = (target.tagName || '').toLowerCase();
                const isTextInput = tag === 'input' || tag === 'select';
                const isTextarea = tag === 'textarea';
                if (!isTextInput && !isTextarea) return;
                if (event.key !== 'Enter' && event.key !== 'NumpadEnter') return;

                // Let regular multiline textareas keep Return. Ctrl/Cmd+Enter submits.
                if (isTextarea && !(event.ctrlKey || event.metaKey)) return;

                event.preventDefault();
                event.stopPropagation();

                const form = target.closest('form');
                if (form && clickFirstVisibleButton(form)) return;

                const block = findInputBlock(target);
                clickFirstVisibleButton(block);
            }, true);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


def _init_state():
    defaults = {
        "authenticated": False,
        "user": None,
        "selected_page": "dashboard",
        "token_page": 1,
        "chat_more_menu": False,
        "chat_notice": True,
        "chat_mute": False,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _go(page_name: str):
    st.session_state.selected_page = page_name


def _logout():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.selected_page = "dashboard"


def _render_header():
    st.markdown(
        """
        <div class="brand-card centered-content" style="max-width: 1100px; margin: 0.2rem auto 0.35rem;">
            <h1>⚡ Dropz Universal Agent</h1>
            <div class="muted">Secure client access • AI automation • Trade center</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_menu():
    """
    Top menu uses the same Streamlit layout logic as the eBay app:
    - keyed container: st-key-top_menu_area
    - one compact row on mobile
    - primary button type for the active page
    Existing Dropz routes and logout behavior stay unchanged.
    """
    with st.container(key="top_menu_area"):
        st.markdown('<div class="top-menu-wrap">', unsafe_allow_html=True)

        menu_labels = [
            "Dashboard",
            "Education",
            "TradeSmart",
            "Chat",
            "Tools",
            "Settings",
            "Logout",
        ]

        menu_cols = st.columns(len(menu_labels), gap="small")

        current_page = (
            "education"
            if st.session_state.selected_page == "accounts"
            else st.session_state.selected_page
        )

        for index, label in enumerate(menu_labels):
            with menu_cols[index]:
                page_key = label.lower()
                is_active = page_key == current_page

                if label == "Logout":
                    st.button(
                        "Logout",
                        use_container_width=True,
                        key=f"top_{label}",
                        on_click=_logout,
                    )
                else:
                    if st.button(
                        label,
                        use_container_width=True,
                        key=f"top_{label}",
                        type="primary" if is_active else "secondary",
                    ):
                        _go(page_key)
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def _render_page():
    user = st.session_state.user or {}
    role = user.get("role", "client")
    page = st.session_state.selected_page

    if page == "dashboard":
        render_frontend_dashboard_page(role)
    elif page in {"education", "accounts"}:
        # Support the new Education route and the old Accounts route so saved sessions do not break.
        if page == "accounts":
            st.session_state.selected_page = "education"
        render_frontend_education_page(role)
    elif page == "tradesmart":
        render_frontend_tradesmart_page()
    elif page == "chat":
        render_frontend_chat_page(role)
    elif page == "tools":
        render_frontend_tools_page(role)
    elif page == "settings":
        if role == "ceo":
            render_settings_ceo_page(role)
        else:
            render_settings_client_page(role)
    else:
        st.session_state.selected_page = "dashboard"
        render_frontend_dashboard_page(role)


def main():
    _init_state()
    _inject_global_enter_submit()

    # Optional safe debug. Add DEBUG_SECRETS=true in Streamlit secrets only when testing.
    if str(get_secret("DEBUG_SECRETS", "")).lower() == "true":
        st.info(
            {
                "CEO_SECRET_PHRASE_loaded": bool(CEO_SECRET_PHRASE),
                "SUPABASE_URL_loaded": bool(SUPABASE_URL),
                "SUPABASE_ANON_KEY_loaded": bool(SUPABASE_ANON_KEY),
                "DROPZ_UPDATE_MANIFEST_URL_loaded": bool(DROPZ_UPDATE_MANIFEST_URL),
            }
        )

    if not st.session_state.authenticated:
        render_frontend_login_page()
        return

    _render_header()
    _render_menu()
    _render_page()


if __name__ == "__main__":
    main()