import streamlit as st

def render_activity_feed():

    st.markdown("""
    <div class="glass-card">
        <h3>Activity Feed</h3>

        <div class="activity-item">
            ✓ 5-win streak achieved
        </div>

        <div class="activity-item">
            ✓ Best trading day this month
        </div>

        <div class="activity-item">
            ✓ New strategy uploaded
        </div>
    </div>
    """, unsafe_allow_html=True)