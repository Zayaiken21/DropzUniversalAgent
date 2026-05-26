from __future__ import annotations

import pandas as pd
import streamlit as st


def _profit_style(value):
    try:
        amount = float(value)
    except Exception:
        return ""
    if amount > 0:
        return "color: #00ffa3; font-weight: 800;"
    if amount < 0:
        return "color: #ff6b88; font-weight: 800;"
    return "color: rgba(255,255,255,.78);"


def render_last_10_trades(trades):
    st.markdown("### Last 10 XAUUSD Trades")

    if not trades:
        st.info("No recent closed XAUUSD trades found yet.")
        return

    df = pd.DataFrame(trades)

    preferred = ["Closed", "Direction", "Symbol", "Volume", "Price", "Profit", "Ticket", "Order", "Comment"]
    ordered = [col for col in preferred if col in df.columns] + [col for col in df.columns if col not in preferred]
    df = df[ordered].head(10)

    try:
        styled = df.style.map(_profit_style, subset=["Profit"])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=390)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=390)


def render_open_xauusd_positions(_positions):
    """Kept as a no-op for backwards imports. Open positions now live inside the MT5 account card."""
    return None
