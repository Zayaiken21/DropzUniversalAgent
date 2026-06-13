from __future__ import annotations

import pandas as pd
import streamlit as st


def _profit_style(value):
    try:
        amount = float(value)
    except Exception:
        return ""
    if amount > 0:
        return "color:#00ffa3;font-weight:800;"
    if amount < 0:
        return "color:#ff6b88;font-weight:800;"
    return "color:rgba(255,255,255,.78);"


def _direction_style(value):
    text = str(value or "").upper()
    if text == "BUY":
        return "color:#00ffa3;font-weight:800;background:rgba(0,255,163,.10);border-radius:8px;padding:3px 10px;"
    if text == "SELL":
        return "color:#ff6b88;font-weight:800;background:rgba(255,107,136,.10);border-radius:8px;padding:3px 10px;"
    return "color:rgba(255,255,255,.65);"


def render_last_10_trades(trades):
    st.markdown(
        '<div class="du-section-head">'
        '<span class="du-section-icon">📒</span>'
        '<span class="du-section-title-text">Last 10 XAUUSD Trades</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not trades:
        st.markdown(
            '<div class="du-empty-state">'
            '<div class="du-empty-icon">🗒️</div>'
            '<div class="du-empty-title">No closed trades yet</div>'
            '<div class="du-empty-sub">Your last 10 closed XAUUSD trades will appear here once available.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(trades)

    preferred = ["Closed", "Direction", "Symbol", "Volume", "Price", "Profit", "Ticket", "Order", "Comment"]
    ordered = [col for col in preferred if col in df.columns] + [col for col in df.columns if col not in preferred]
    df = df[ordered].head(10)

    try:
        styled = df.style
        if "Profit" in df.columns:
            styled = styled.map(_profit_style, subset=["Profit"])
        if "Direction" in df.columns:
            styled = styled.map(_direction_style, subset=["Direction"])
        if "Profit" in df.columns:
            styled = styled.format({"Profit": "{:,.2f}"})
        if "Volume" in df.columns:
            styled = styled.format({"Volume": "{:,.2f}"})
        if "Price" in df.columns:
            styled = styled.format({"Price": "{:,.2f}"})
        st.dataframe(styled, use_container_width=True, hide_index=True, height=390)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=390)


def render_open_xauusd_positions(_positions):
    """Kept as a no-op for backwards imports. Open positions now live inside the MT5 account card."""
    return None
