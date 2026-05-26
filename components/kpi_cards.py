from __future__ import annotations
import streamlit as st

def render_kpi_cards(data):
    account = data.get("account", {})
    metrics = data.get("metrics", {})
    currency = account.get("currency", "—")

    cards = [
        ("Balance", f"{account.get('balance', 0):,.2f} {currency}", "Live MT5 balance"),
        ("Equity", f"{account.get('equity', 0):,.2f} {currency}", "Live MT5 equity"),
        ("Daily P/L", f"{metrics.get('daily_pnl', 0):,.2f} {currency}", "Today"),
        ("Win Rate", f"{metrics.get('win_rate', 0):.1f}%", f"{metrics.get('closed_trades', 0)} closed trades"),
    ]

    cols = st.columns(4)
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div class="du-kpi-card"><div class="du-kpi-label">{label}</div><div class="du-kpi-value">{value}</div><div class="du-kpi-sub">{sub}</div></div>',
                unsafe_allow_html=True,
            )
