import streamlit as st

def render_kpi_cards(summary):

    cols = st.columns(4)

    cards = [
        ("Win Rate", f"{summary['winRate']}%"),
        ("Total PnL", f"${summary['profit']}"),
        ("Trades", summary['totalTrades']),
        ("Current Streak", summary['streak'])
    ]

    for col, card in zip(cols, cards):
        with col:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-title">{card[0]}</div>
                <div class="kpi-value">{card[1]}</div>
            </div>
            """, unsafe_allow_html=True)