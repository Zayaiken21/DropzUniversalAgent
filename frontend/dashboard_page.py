from __future__ import annotations

import streamlit as st

from components.dashboard_mt5_data import get_live_mt5_dashboard_data
from components.dashboard_quotes import get_daily_session_quote
from components.kpi_cards import render_kpi_cards
from components.tables import render_last_10_trades
from components.activity_feed import render_activity_feed
from components.charts import render_performance_charts


def _inject_dashboard_styles():
    st.markdown("""
<style>
.du-dashboard-hero{padding:28px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.09),rgba(255,255,255,.03));border:1px solid rgba(255,255,255,.12);box-shadow:0 18px 60px rgba(0,0,0,.28);margin-bottom:22px}
.du-dashboard-title{font-size:34px;font-weight:900;color:#fff;margin-bottom:6px}.du-dashboard-sub{color:rgba(255,255,255,.65);font-size:15px}
.du-card{padding:22px;border-radius:22px;background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.025));border:1px solid rgba(255,255,255,.10);box-shadow:0 16px 46px rgba(0,0,0,.24);margin-bottom:18px}
.du-kpi-card{padding:18px;border-radius:20px;background:linear-gradient(145deg,rgba(255,255,255,.085),rgba(255,255,255,.03));border:1px solid rgba(255,255,255,.105);box-shadow:0 14px 38px rgba(0,0,0,.20);min-height:118px}
.du-kpi-label{color:rgba(255,255,255,.55);font-size:12px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase}.du-kpi-value{color:#fff;font-size:26px;font-weight:900;margin-top:10px}.du-kpi-sub{color:rgba(255,255,255,.55);font-size:12px;margin-top:8px}
.du-quote{padding:24px;border-radius:24px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.12);margin-bottom:20px}.du-quote-good{box-shadow:0 0 35px rgba(0,255,163,.18);border-color:rgba(0,255,163,.30)}.du-quote-bad{box-shadow:0 0 35px rgba(255,77,109,.20);border-color:rgba(255,77,109,.32)}
.du-quote-label{color:rgba(255,255,255,.55);font-size:12px;text-transform:uppercase;letter-spacing:1.2px;font-weight:900;margin-bottom:10px}.du-quote-text{color:#fff;font-size:18px;font-weight:750;line-height:1.45}
.du-mini-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.du-mini{padding:14px;border-radius:16px;background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.08)}.du-mini-label{color:rgba(255,255,255,.52);font-size:12px;font-weight:800;text-transform:uppercase}.du-mini-value{color:#fff;font-size:18px;font-weight:900;margin-top:6px}
.du-status-online{color:#00ffa3}.du-status-offline{color:#ff6b88}
.du-activity-item{padding:12px 0;color:rgba(255,255,255,.82);border-bottom:1px solid rgba(255,255,255,.08)}
</style>""", unsafe_allow_html=True)


def _render_live_account(data):
    account = data.get("account", {})
    metrics = data.get("metrics", {})
    status = "Online" if data.get("online") else "Offline"
    status_class = "du-status-online" if data.get("online") else "du-status-offline"
    symbol = data.get("symbol", "XAUUSD")
    balance = account.get("balance", 0)
    equity = account.get("equity", 0)
    currency = account.get("currency", "—")
    login = account.get("login", "—")
    server = account.get("server", "—")
    open_positions = metrics.get("open_positions", 0)
    open_profit = metrics.get("open_profit", 0)

    st.markdown("### Live MT5 Account")
    st.markdown(
        f"""
        <div class="du-card">
            <div class="du-mini-grid">
                <div class="du-mini"><div class="du-mini-label">Status</div><div class="du-mini-value {status_class}">{status}</div></div>
                <div class="du-mini"><div class="du-mini-label">Symbol</div><div class="du-mini-value">{symbol}</div></div>
                <div class="du-mini"><div class="du-mini-label">Balance</div><div class="du-mini-value">{balance:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">Equity</div><div class="du-mini-value">{equity:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">Open Trades</div><div class="du-mini-value">{open_positions}</div></div>
                <div class="du-mini"><div class="du-mini-label">Open P/L</div><div class="du-mini-value">{open_profit:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">Account</div><div class="du-mini-value">{login}</div></div>
                <div class="du-mini"><div class="du-mini-label">Server</div><div class="du-mini-value">{server}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_quote(data):
    quote = get_daily_session_quote(data.get("metrics", {}))
    st.markdown(
        f'<div class="du-quote {quote["glow_class"]}"><div class="du-quote-label">Session Quote</div><div class="du-quote-text">{quote["quote"]}</div></div>',
        unsafe_allow_html=True,
    )


def render_frontend_dashboard_page(role=None):
    _inject_dashboard_styles()

    # Uses the active MT5 terminal/session opened by TradeSmart or local MT5.
    data = get_live_mt5_dashboard_data("XAUUSD")

    st.markdown(
        '<div class="du-dashboard-hero"><div class="du-dashboard-title">⚡ Trading Intelligence</div><div class="du-dashboard-sub">Live XAUUSD trade journal, account performance, and progress feedback.</div></div>',
        unsafe_allow_html=True,
    )

    _render_quote(data)
    render_kpi_cards(data)

    left, right = st.columns([2, 1])

    with left:
        render_last_10_trades(data.get("last_10_trades", []))
        st.markdown("### Performance Journal")
        render_performance_charts(data)

    with right:
        _render_live_account(data)
        render_activity_feed(data)
