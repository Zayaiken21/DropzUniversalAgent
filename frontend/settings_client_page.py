import streamlit as st

def render_settings_client_page(role):
    st.markdown(
        """
        <div class="glass-card centered-content">
            <h1>👤 Client Settings</h1>
            <h3>Manage Client Access</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Client Settings")
    st.write(f"Current role: {role}")

    st.markdown(
        """
        <div class="glass-card">
            <p class="muted">
                This page is for client-side settings and access management.
                Keep your client options here so the rest of the app stays clean.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    from frontend.mt5_settings_component import render_mt5_credentials_settings
    render_mt5_credentials_settings(role)
