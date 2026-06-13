import streamlit as st
from frontend.style_loader import load_theme_css
from frontend.database import (
    validate_ceo_password,
    validate_client_login,
    validate_token,
    set_client_profile,
    reset_client_password_with_token,
)


def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _clear_profile_flow():
    for key in (
        "pending_profile_token",
        "pending_profile_user",
        "profile_setup_required",
        "pending_password_token",
        "pending_password_user",
        "password_setup_required",
        "reset_password_mode",
    ):
        st.session_state.pop(key, None)


def _finish_client_login(user: dict):
    st.session_state.authenticated = True
    st.session_state.user = dict(user)
    st.session_state.selected_page = "dashboard"
    _clear_profile_flow()
    _rerun()


# ── copy-paste enabler injected once per page load ────────────────────────────
def _inject_copy_paste():
    """
    Removes any clipboard / paste blockers that Streamlit or the OS might
    impose on input fields. Also ensures all inputs allow right-click.
    """
    st.markdown(
        """
        <script>
        (function () {
            if (window.__dropzCopyPasteInstalled) return;
            window.__dropzCopyPasteInstalled = true;
            function unlockField(el) {
                ['copy','cut','paste','contextmenu'].forEach(function(ev) {
                    el.addEventListener(ev, function(e) { e.stopPropagation(); }, true);
                });
                el.removeAttribute('oncopy');
                el.removeAttribute('oncut');
                el.removeAttribute('onpaste');
            }
            function processAll() {
                document.querySelectorAll('input, textarea').forEach(unlockField);
            }
            processAll();
            var obs = new MutationObserver(processAll);
            obs.observe(document.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


# ── first-time account setup (after entering token as username) ───────────────

def _render_first_time_profile_setup():
    _inject_copy_paste()
    pending_token = (
        st.session_state.get("pending_profile_token")
        or st.session_state.get("pending_password_token", "")
    )
    pending_user  = (
        st.session_state.get("pending_profile_user")
        or st.session_state.get("pending_password_user", {})
        or {}
    )
    client_name = pending_user.get("name", "Client")

    st.markdown('<div style="margin-top: 0.05rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass-card centered-content" style="max-width: 580px; margin: 0 auto;">',
        unsafe_allow_html=True,
    )
    st.markdown("<h1>⚡ Dropz Universal Agent</h1>", unsafe_allow_html=True)
    st.markdown("### 🔐 Finish Account Setup")
    st.info(
        f"Welcome, **{client_name}**. Your first-time access code worked. "
        "Now create the **username** and **password** you will use every time you log in."
    )

    with st.form("first_time_profile_form", clear_on_submit=False):
        username = st.text_input(
            "Choose a Username",
            key="first_time_username",
            placeholder="e.g. john_doe  (letters, numbers, dots, underscores, hyphens)",
            help="This becomes your permanent login username. Min 3 characters.",
        )
        new_password = st.text_input(
            "Create a Password",
            key="first_time_new_password",
            type="password",
            placeholder="At least 6 characters",
        )
        confirm_password = st.text_input(
            "Confirm Password",
            key="first_time_confirm_password",
            type="password",
            placeholder="Re-enter your password",
        )
        submit = st.form_submit_button("Save & Open Dashboard", use_container_width=True)

        if submit:
            if not pending_token:
                st.error("Session expired. Go back and sign in with your first-time access code again.")
            elif not username or not new_password or not confirm_password:
                st.error("⚠️ Please fill in all three fields.")
            elif new_password != confirm_password:
                st.error("❌ Passwords do not match.")
            else:
                try:
                    updated_user = set_client_profile(pending_token, username, new_password)
                    st.success("✅ Account set up. Logging you in…")
                    _finish_client_login(updated_user)
                except Exception as exc:
                    st.error(str(exc))

    if st.button("← Back to Login", use_container_width=True, key="setup_back"):
        _clear_profile_flow()
        _rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ── reset password form ───────────────────────────────────────────────────────

def _render_reset_password_form():
    _inject_copy_paste()

    st.markdown("### 🔁 Reset Your Password")
    st.info(
        "Enter the **original access code** you received from the CEO when your account was created. "
        "This is the code you used the very first time you logged in — it never changes and is "
        "required to reset your password."
    )

    with st.form("reset_client_password_form", clear_on_submit=False):
        reset_token = st.text_input(
            "Original Access Code",
            key="reset_client_access_code",
            placeholder="Paste or type your original access code here",
            help="The access code from the CEO. You can paste it directly into this field.",
        )
        new_password = st.text_input(
            "New Password",
            key="reset_new_password",
            type="password",
            placeholder="Enter your new password (min 6 characters)",
        )
        confirm_password = st.text_input(
            "Confirm New Password",
            key="reset_confirm_password",
            type="password",
            placeholder="Re-enter your new password",
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            reset_clicked = st.form_submit_button("Save New Password", use_container_width=True)
        with col2:
            cancel_clicked = st.form_submit_button("← Back to Login", use_container_width=True)

        if cancel_clicked:
            _clear_profile_flow()
            _rerun()

        if reset_clicked:
            if not reset_token:
                st.error("⚠️ Paste your original access code above.")
            elif not new_password or not confirm_password:
                st.error("⚠️ Enter and confirm your new password.")
            elif new_password != confirm_password:
                st.error("❌ Passwords do not match.")
            else:
                try:
                    user = validate_token(reset_token)
                    if not user:
                        st.error("❌ Invalid or expired access code. Contact your administrator.")
                        return
                    reset_client_password_with_token(reset_token, new_password)
                    display_name = user.get("username") or user.get("name") or "your account"
                    st.success(
                        f"✅ Password reset for **{display_name}**. "
                        "You can now log in with your username and new password."
                    )
                    _clear_profile_flow()
                    _rerun()
                except Exception as exc:
                    st.error(str(exc))


# ── main login page ───────────────────────────────────────────────────────────

def render_frontend_login_page():
    load_theme_css()
    _inject_copy_paste()

    # If we are mid-flow (first-time setup), show that screen instead
    if (
        st.session_state.get("profile_setup_required")
        or st.session_state.get("password_setup_required")
    ):
        _render_first_time_profile_setup()
        return

    st.markdown('<div style="margin-top: 0.05rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass-card centered-content" style="max-width: 580px; margin: 0 auto;">',
        unsafe_allow_html=True,
    )
    st.markdown('<h1>⚡ Dropz Universal Agent</h1>', unsafe_allow_html=True)
    st.markdown("### 🔐 Login to Access Your Account")

    login_type = st.radio(
        "Select Login Type",
        ["CEO Login", "Client Login"],
        key="login_type",
        horizontal=True,
    )

    # ── password reset sub-screen ─────────────────────────────────────────────
    if login_type == "Client Login" and st.session_state.get("reset_password_mode"):
        _render_reset_password_form()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── main login form ───────────────────────────────────────────────────────
    with st.form(key="login_form", clear_on_submit=False):

        if login_type == "CEO Login":
            # ── CEO path ──────────────────────────────────────────────────────
            st.markdown("**Enter CEO Password**")
            ceo_password = st.text_input(
                "Password",
                key="ceo_password",
                type="password",
                placeholder="Enter CEO password",
            )
            submit_clicked  = st.form_submit_button("Login", use_container_width=True)
            reset_clicked   = False
            username_or_code = ""
            client_password  = ""

        else:
            # ── Client path ───────────────────────────────────────────────────
            st.markdown("**Client Login**")

            username_or_code = st.text_input(
                "Username",
                key="client_username",
                placeholder="Enter your username",
                # ↑ No mention of token. New users whose only identifier IS
                #   the token will type/paste it here; the backend accepts both.
                help=(
                    "Enter your username. "
                    "First-time users: paste the access code you received — "
                    "leave the password blank and you will be prompted to create your credentials."
                ),
            )
            client_password = st.text_input(
                "Password",
                key="client_password",
                type="password",
                placeholder="Enter your password",
                help="Leave blank if this is your very first login.",
            )
            st.caption(
                "First time logging in? Enter your access code as the username, "
                "leave the password blank, then follow the prompts to create your username and password."
            )

            col1, col2 = st.columns([1, 1])
            with col1:
                submit_clicked = st.form_submit_button("Login", use_container_width=True)
            with col2:
                reset_clicked = st.form_submit_button("Forgot Password?", use_container_width=True)

        # ── form logic ────────────────────────────────────────────────────────
        if submit_clicked:
            if login_type == "CEO Login":
                if ceo_password:
                    user = validate_ceo_password(ceo_password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user = dict(user)
                        st.session_state.selected_page = "dashboard"
                        _rerun()
                    else:
                        st.error("❌ Incorrect password.")
                else:
                    st.error("⚠️ Please enter a password.")

            else:  # Client login
                if username_or_code:
                    try:
                        user = validate_client_login(username_or_code, client_password)
                    except Exception as exc:
                        st.error(str(exc))
                        user = None

                    if user and (
                        user.get("requires_profile_setup")
                        or user.get("requires_password_setup")
                    ):
                        # First-time login — route to account setup
                        st.session_state.pending_profile_token = (
                            str(user.get("token") or username_or_code).strip().upper()
                        )
                        st.session_state.pending_profile_user  = dict(user)
                        st.session_state.profile_setup_required = True
                        _rerun()

                    elif user and user.get("password_required"):
                        st.error("🔐 Password required. Enter the password for this username.")

                    elif user and user.get("login_ok", True):
                        _finish_client_login(user)

                    else:
                        st.error("❌ Invalid username or password.")
                else:
                    st.error("⚠️ Please enter your username.")

        if reset_clicked:
            st.session_state.reset_password_mode = True
            _rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ── shim for any callers using the old name ───────────────────────────────────
def render_login_page():
    return render_frontend_login_page()
