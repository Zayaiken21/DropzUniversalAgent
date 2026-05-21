import streamlit as st
from frontend.style_loader import load_theme_css
from frontend.database import get_all_client_tokens, delete_user_by_token, cancel_all_client_tokens, generate_client_token

def render_settings_ceo_page(role):
    load_theme_css()
    st.markdown('<h2 class="section-title">⚙️ CEO Settings</h2>', unsafe_allow_html=True)

    if "token_page" not in st.session_state:
        st.session_state.token_page = 1

    st.markdown('<div class="glass-card centered-content">', unsafe_allow_html=True)
    st.markdown("### 🎫 Generate Client Token")
    name = st.text_input("Client Name", placeholder="Enter client name")

    if st.button("Generate Token", use_container_width=True):
        if name:
            token = generate_client_token(name, 1)
            st.success(f"✅ Generated token for **{name}**")
            st.code(token, language=None)
        else:
            st.error("⚠️ Please enter a client name.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="glass-card centered-content">', unsafe_allow_html=True)
    st.markdown("### 🗂️ Manage Client Tokens & Accounts")

    all_tokens = get_all_client_tokens()
    active_tokens = [u for u in all_tokens if u["active"] == 1]
    total_pages = max(1, (len(active_tokens) + 4) // 5)
    start = (st.session_state.token_page - 1) * 5
    end = start + 5
    tokens_page = active_tokens[start:end]

    if not tokens_page:
        st.markdown('<div class="glass-card muted centered-content">No active client tokens</div>', unsafe_allow_html=True)
    else:
        for user in tokens_page:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{user['name']}** — `{user['token']}`")
            with col2:
                if st.button("❌ Delete", key=f"delete_{user['token']}", use_container_width=True):
                    delete_user_by_token(user["token"])
                    st.success(f"✅ Deleted token for {user['name']}")
                    st.rerun()
            with col3:
                st.markdown("*Active*")

        st.markdown("---")
        pcol1, pcol2, pcol3 = st.columns([1, 1, 1])
        with pcol1:
            if st.session_state.token_page > 1 and st.button("⬅ Previous", use_container_width=True):
                st.session_state.token_page -= 1
                st.rerun()
        with pcol2:
            st.markdown(f"**Page {st.session_state.token_page} of {total_pages}**")
        with pcol3:
            if st.session_state.token_page < total_pages and st.button("Next ➡", use_container_width=True):
                st.session_state.token_page += 1
                st.rerun()

    st.markdown("---")
    if st.button("🚫 Cancel All Client Tokens", type="primary", use_container_width=True):
        cancel_all_client_tokens()
        st.success("**All client tokens cancelled.**")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)