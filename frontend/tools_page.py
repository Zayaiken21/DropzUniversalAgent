import streamlit as st

def render_tools_page(role):
    st.markdown(
        """
        <div class="glass-card centered-content">
            <h1>🛠️ Tools</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(f"Role: {role}")


def render_frontend_tools_page():
    return None