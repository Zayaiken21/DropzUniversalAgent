import streamlit as st

def render_accounts():
    st.markdown('<h2 class="section-title">Accounts</h2>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass-card muted centered-content">Client account profile, token info, and connected platforms.</div>',
        unsafe_allow_html=True,
    )


def render_frontend_accounts_page():
    return None