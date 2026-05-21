import streamlit as st

def render_frontend_dashboard_page(role):
    st.markdown(
        """
        <div class="glass-card centered-content">
            <h1>⚡ Dashboard</h1>
            <p class="muted">Welcome back.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(f"Current role: {role}")