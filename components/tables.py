import streamlit as st
import pandas as pd

def render_recent_trades(trades):

    st.markdown("""
    <div class="glass-card">
        <h3>Recent Trades</h3>
    </div>
    """, unsafe_allow_html=True)

    df = pd.DataFrame(trades)

    st.dataframe(
        df,
        use_container_width=True,
        height=420
    )