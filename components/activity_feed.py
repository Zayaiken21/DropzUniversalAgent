from __future__ import annotations

import streamlit as st


def _pnl_class(value: float) -> str:
    if value > 0:
        return "du-feed-positive"
    if value < 0:
        return "du-feed-negative"
    return "du-feed-neutral"


def _pnl_icon(value: float) -> str:
    if value > 0:
        return "📈"
    if value < 0:
        return "📉"
    return "➖"


def render_activity_feed(data):
    metrics = data.get("metrics", {})
    trades = data.get("last_10_trades", [])
    account = data.get("account", {})
    currency = account.get("currency", "—")

    daily   = float(metrics.get("daily_pnl", 0) or 0)
    weekly  = float(metrics.get("weekly_pnl", 0) or 0)
    monthly = float(metrics.get("monthly_pnl", 0) or 0)
    open_pnl = float(metrics.get("open_profit", 0) or 0)

    rows = [
        ("Daily P/L",   daily,    "Since midnight"),
        ("Weekly P/L",  weekly,   "Since Monday"),
        ("Monthly P/L", monthly,  "Since the 1st"),
        ("Open P/L",    open_pnl, "Floating on open trades"),
    ]

    st.markdown(
        '<div class="du-section-head">'
        '<span class="du-section-icon">🗞️</span>'
        '<span class="du-section-title-text">Trade Log Feedback</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    items_html = ""

    if trades:
        latest = trades[0]
        latest_profit = float(latest.get("Profit", 0) or 0)
        direction = str(latest.get("Direction", "—")).upper()
        dir_color = "#00ffa3" if direction == "BUY" else ("#ff6b88" if direction == "SELL" else "rgba(255,255,255,.7)")
        items_html += (
            '<div class="du-activity-item">'
            '<span class="du-activity-icon">🕒</span>'
            '<div class="du-activity-body">'
            '<div class="du-activity-title">Latest closed trade</div>'
            f'<div class="du-activity-sub">'
            f'<span style="color:{dir_color};font-weight:800">{direction}</span> '
            f'{latest.get("Symbol", "XAUUSD")} • '
            f'<span class="{_pnl_class(latest_profit)}">{latest_profit:,.2f} {currency}</span>'
            '</div></div></div>'
        )

    for label, value, sub in rows:
        items_html += (
            '<div class="du-activity-item">'
            f'<span class="du-activity-icon">{_pnl_icon(value)}</span>'
            '<div class="du-activity-body">'
            f'<div class="du-activity-title">{label}</div>'
            f'<div class="du-activity-sub {_pnl_class(value)}">{value:,.2f} {currency}'
            f'<span class="du-activity-meta"> · {sub}</span></div>'
            '</div></div>'
        )

    st.markdown(items_html, unsafe_allow_html=True)
