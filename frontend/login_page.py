import streamlit as st
from frontend.style_loader import load_theme_css
from frontend.database import validate_ceo_password, validate_token

def render_frontend_login_page():
    load_theme_css()

    st.markdown('<div style="margin-top: 0.05rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass-card centered-content" style="max-width: 560px; margin: 0 auto;">',
        unsafe_allow_html=True
    )
    st.markdown('<h1>⚡ Dropz Universal Agent</h1>', unsafe_allow_html=True)
    st.markdown("### 🔐 Login to Access Your Account")

    login_type = st.radio(
        "Select Login Type",
        ["CEO Login", "Client Login"],
        key="login_type",
        horizontal=True
    )

    with st.form(key="login_form", clear_on_submit=False):
        if login_type == "CEO Login":
            st.markdown("**Enter CEO Password**")
            password = st.text_input(
                "Password",
                key="ceo_password",
                type="password",
                label_visibility="visible",
                placeholder="Enter CEO password",
                help="Your CEO password"
            )
            submit_clicked = st.form_submit_button("Login", use_container_width=False)
        else:
            st.markdown("**Enter Your 15-Character Client Token**")
            token = st.text_input(
                "Token",
                key="client_token",
                placeholder="Paste or type your token",
                max_chars=15,
                label_visibility="visible",
                help="Your CEO will provide this token"
            )
            submit_clicked = st.form_submit_button("Login", use_container_width=False)

        if submit_clicked:
            if login_type == "CEO Login":
                if password:
                    user = validate_ceo_password(password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user = dict(user)
                        st.session_state.selected_page = "dashboard"
                        st.rerun()
                    else:
                        st.error("❌ Invalid password.")
                else:
                    st.error("⚠️ Please enter a password.")
            else:
                if token:
                    user = validate_token(token)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user = dict(user)
                        st.session_state.selected_page = "dashboard"
                        st.rerun()
                    else:
                        st.error("❌ Invalid or expired token.")
                else:
                    st.error("⚠️ Please enter a token.")

    st.markdown("</div>", unsafe_allow_html=True)

def render_login_page():
    return render_frontend_login_page()