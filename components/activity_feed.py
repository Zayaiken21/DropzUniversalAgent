from __future__ import annotations

import streamlit as st


def render_activity_feed(data):
    metrics = data.get("metrics", {})
    trades = data.get("last_10_trades", [])
    account = data.get("account", {})
    currency = account.get("currency", "—")

    items = [
        f"Daily P/L: {metrics.get('daily_pnl', 0):,.2f} {currency}",
        f"Weekly P/L: {metrics.get('weekly_pnl', 0):,.2f} {currency}",
        f"Monthly P/L: {metrics.get('monthly_pnl', 0):,.2f} {currency}",
        f"Open trade P/L: {metrics.get('open_profit', 0):,.2f} {currency}",
    ]

    if trades:
        latest = trades[0]
        items.insert(
            0,
            f"Latest closed trade: {latest.get('Direction', '—')} {latest.get('Symbol', 'XAUUSD')} • P/L {latest.get('Profit', 0):,.2f} {currency}",
        )

    st.markdown("### Trade Journal Feedback")
    for item in items:
        st.markdown(f'<div class="du-activity-item">{item}</div>', unsafe_allow_html=True)
