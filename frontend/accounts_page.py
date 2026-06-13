import streamlit as st
from datetime import datetime, timedelta
import random


PAGE_CONFIG = {
    "name": "Trading Accounts",
    "icon": "📈",
    "roles": ["ceo", "client", "admin", "trader"],
}


def _inject_trading_accounts_css():
    st.markdown(
        """
        <style>
        .trade-hero {
            padding: 1.5rem;
            border-radius: 24px;
            background: radial-gradient(circle at top left, rgba(255, 199, 44, .28), transparent 32%),
                        linear-gradient(135deg, rgba(18,18,18,.96), rgba(37,29,5,.92));
            border: 1px solid rgba(255, 207, 64, .28);
            box-shadow: 0 18px 50px rgba(0,0,0,.25);
            margin-bottom: 1rem;
        }
        .trade-hero h1 {
            margin: 0;
            font-size: clamp(2rem, 5vw, 3.5rem);
            letter-spacing: -0.04em;
            color: #fff7d1;
        }
        .trade-hero p {
            max-width: 980px;
            color: rgba(255,255,255,.78);
            font-size: 1.02rem;
            margin-top: .65rem;
        }
        .trade-badge-row {
            display:flex;
            flex-wrap:wrap;
            gap:.55rem;
            margin-top: 1rem;
        }
        .trade-badge {
            border: 1px solid rgba(255, 218, 92, .26);
            background: rgba(255,255,255,.07);
            color:#ffeaa0;
            border-radius:999px;
            padding:.42rem .7rem;
            font-size:.83rem;
            font-weight:700;
        }
        .trade-card {
            padding: 1.05rem;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.035));
            border: 1px solid rgba(255,255,255,.12);
            box-shadow: 0 14px 30px rgba(0,0,0,.18);
            min-height: 132px;
        }
        .trade-card h3 {
            margin: 0 0 .45rem 0;
            font-size: 1rem;
            color: #fff1b3;
        }
        .trade-big {
            font-size: 1.8rem;
            font-weight: 900;
            color: white;
            letter-spacing: -0.03em;
        }
        .trade-muted { color: rgba(255,255,255,.66); font-size:.9rem; }
        .status-live { color: #82ffb2; font-weight:900; }
        .status-demo { color: #9ed0ff; font-weight:900; }
        .status-risk { color: #ffd36b; font-weight:900; }
        .account-tile {
            padding: 1rem;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(13,13,13,.55);
            margin-bottom: .75rem;
        }
        .account-tile strong { color: #fff0aa; }
        .signal-box {
            padding: 1rem;
            border-radius: 18px;
            background: rgba(255,255,255,.055);
            border: 1px solid rgba(255,255,255,.10);
            margin-bottom: .7rem;
        }
        .signal-buy { border-left: 5px solid #7cffac; }
        .signal-sell { border-left: 5px solid #ff8a8a; }
        .signal-wait { border-left: 5px solid #ffd76f; }
        .tiny-pill {
            display:inline-block;
            padding:.22rem .52rem;
            border-radius:999px;
            background:rgba(255,255,255,.08);
            margin:.12rem;
            font-size:.78rem;
            color:rgba(255,255,255,.8);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _money(v):
    return f"${v:,.2f}"


def _mock_accounts():
    return [
        {
            "name": "TradeSmart Live",
            "broker": "TradeSmart-Server01",
            "login": "53922",
            "type": "LIVE",
            "balance": 24850.42,
            "equity": 25110.77,
            "drawdown": "2.1%",
            "risk": "Low",
            "symbols": ["XAUUSD", "NAS100", "US30"],
        },
        {
            "name": "Strategy Lab Demo",
            "broker": "TradeSmart-Demo",
            "login": "87291",
            "type": "DEMO",
            "balance": 100000.00,
            "equity": 101842.15,
            "drawdown": "0.8%",
            "risk": "Testing",
            "symbols": ["XAUUSD", "EURUSD", "GBPJPY"],
        },
        {
            "name": "Prop Challenge Mock",
            "broker": "FTMO-Trial",
            "login": "11407",
            "type": "TRIAL",
            "balance": 50000.00,
            "equity": 50731.65,
            "drawdown": "1.4%",
            "risk": "Medium",
            "symbols": ["NAS100", "XAUUSD"],
        },
    ]


def _mock_signals():
    now = datetime.now()
    return [
        {
            "bias": "BUY",
            "symbol": "XAUUSD",
            "setup": "Liquidity sweep + bullish displacement",
            "entry": "2364.20 - 2366.10",
            "sl": "2359.40",
            "tp": "2378.80",
            "confidence": "82%",
            "time": (now - timedelta(minutes=4)).strftime("%I:%M %p"),
        },
        {
            "bias": "WAIT",
            "symbol": "NAS100",
            "setup": "Waiting for 5M close above range high",
            "entry": "No entry yet",
            "sl": "Auto after trigger",
            "tp": "1:3 RR projection",
            "confidence": "61%",
            "time": (now - timedelta(minutes=9)).strftime("%I:%M %p"),
        },
        {
            "bias": "SELL",
            "symbol": "US30",
            "setup": "Bearish order block reaction",
            "entry": "39120 - 39145",
            "sl": "39192",
            "tp": "38970",
            "confidence": "74%",
            "time": (now - timedelta(minutes=16)).strftime("%I:%M %p"),
        },
    ]


def _render_signal(signal):
    css = {
        "BUY": "signal-buy",
        "SELL": "signal-sell",
        "WAIT": "signal-wait",
    }.get(signal["bias"], "signal-wait")
    st.markdown(
        f"""
        <div class="signal-box {css}">
            <strong>{signal['symbol']} • {signal['bias']}</strong>
            <div class="trade-muted">{signal['setup']} • {signal['time']}</div>
            <div style="margin-top:.55rem;">
                <span class="tiny-pill">Entry: {signal['entry']}</span>
                <span class="tiny-pill">SL: {signal['sl']}</span>
                <span class="tiny-pill">TP: {signal['tp']}</span>
                <span class="tiny-pill">Confidence: {signal['confidence']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trading_accounts_page(role="client"):
    _inject_trading_accounts_css()

    st.markdown(
        """
        <div class="trade-hero">
            <h1>Trading Command Center</h1>
            <p>Connect trading accounts, test account health, simulate risk, review mock signals, and preview the kind of trading dashboard your clients can use before real broker execution is enabled.</p>
            <div class="trade-badge-row">
                <span class="trade-badge">MT5 Ready Mockup</span>
                <span class="trade-badge">Live/Demo Profiles</span>
                <span class="trade-badge">Risk Guard</span>
                <span class="trade-badge">Signal Lab</span>
                <span class="trade-badge">Client Friendly</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    accounts = _mock_accounts()
    live_accounts = [a for a in accounts if a["type"] == "LIVE"]
    total_equity = sum(a["equity"] for a in accounts)
    total_balance = sum(a["balance"] for a in accounts)
    pnl = total_equity - total_balance

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="trade-card"><h3>Total Equity</h3><div class="trade-big">{_money(total_equity)}</div><div class="trade-muted">Mock combined accounts</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="trade-card"><h3>Floating P/L</h3><div class="trade-big">{_money(pnl)}</div><div class="trade-muted">Trial dashboard value</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="trade-card"><h3>Live Accounts</h3><div class="trade-big">{len(live_accounts)}</div><div class="trade-muted">Connected profile mock</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="trade-card"><h3>Risk Guard</h3><div class="trade-big">ON</div><div class="trade-muted">Daily loss + max trades check</div></div>', unsafe_allow_html=True)

    tab_accounts, tab_connect, tab_risk, tab_signals, tab_journal = st.tabs([
        "🏦 Accounts",
        "🔌 Connect Broker",
        "🛡️ Risk Lab",
        "⚡ Signal Lab",
        "📓 Trade Journal",
    ])

    with tab_accounts:
        st.subheader("Account Profiles")
        for account in accounts:
            status = "status-live" if account["type"] == "LIVE" else "status-demo"
            symbols = " ".join([f'<span class="tiny-pill">{s}</span>' for s in account["symbols"]])
            st.markdown(
                f"""
                <div class="account-tile">
                    <div style="display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;">
                        <div>
                            <strong>{account['name']}</strong><br>
                            <span class="trade-muted">{account['broker']} • Login {account['login']}</span>
                        </div>
                        <div class="{status}">{account['type']}</div>
                    </div>
                    <div style="margin-top:.7rem;display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.6rem;">
                        <span class="tiny-pill">Balance: {_money(account['balance'])}</span>
                        <span class="tiny-pill">Equity: {_money(account['equity'])}</span>
                        <span class="tiny-pill">Drawdown: {account['drawdown']}</span>
                        <span class="tiny-pill">Risk: {account['risk']}</span>
                    </div>
                    <div style="margin-top:.55rem;">{symbols}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.info("These are trial profiles only. Replace the mock data with your real MT5 connection status when ready.")

    with tab_connect:
        st.subheader("Broker Connection Tester")
        with st.form("mock_broker_connection_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                broker_server = st.text_input("Broker server", value="TradeSmart-Server01")
                login = st.text_input("MT5 login", value="53922")
                profile_type = st.selectbox("Profile type", ["Demo", "Live", "Prop Trial"])
            with col_b:
                symbol = st.selectbox("Primary symbol", ["XAUUSD", "NAS100", "US30", "EURUSD", "GBPUSD"])
                risk_mode = st.selectbox("Risk mode", ["Conservative", "Balanced", "Aggressive", "Manual Only"])
                nickname = st.text_input("Account nickname", value="My Trading Account")
            submitted = st.form_submit_button("Run Mock Connection Test")
        if submitted:
            st.success(f"Mock connection passed for {nickname}. Server: {broker_server}, Login: {login}, Symbol: {symbol}, Mode: {risk_mode}.")
            st.progress(92)
            st.caption("Mock result: terminal found, account authorized, symbol visible, trading permissions detected.")

        st.markdown("### Launch Checklist")
        st.checkbox("MT5 terminal installed", value=True)
        st.checkbox("Broker server name matches exact Demo/Live server", value=True)
        st.checkbox("Algo trading enabled", value=False)
        st.checkbox("Symbol is visible in Market Watch", value=True)
        st.checkbox("Daily loss and max trades configured", value=True)

    with tab_risk:
        st.subheader("Risk Simulator")
        col1, col2, col3 = st.columns(3)
        with col1:
            balance = st.number_input("Account balance", min_value=100.0, value=25000.0, step=500.0)
            risk_pct = st.slider("Risk per trade %", 0.1, 5.0, 1.0, 0.1)
        with col2:
            stop_loss_points = st.number_input("Stop loss points/pips", min_value=1.0, value=50.0, step=1.0)
            value_per_lot = st.number_input("Value per point per 1.00 lot", min_value=0.1, value=10.0, step=0.5)
        with col3:
            rr = st.slider("Reward ratio", 1.0, 5.0, 3.0, 0.25)
            max_trades = st.slider("Max trades/day", 1, 15, 4)
        risk_dollars = balance * (risk_pct / 100)
        lots = risk_dollars / (stop_loss_points * value_per_lot)
        reward = risk_dollars * rr
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Risk $", _money(risk_dollars))
        r2.metric("Suggested Lot", f"{lots:.2f}")
        r3.metric("Target Reward", _money(reward))
        r4.metric("Daily Max Risk", _money(risk_dollars * max_trades))
        st.warning("This is a calculator mockup, not financial advice. Connect real tick value and contract specs before live trading.")

    with tab_signals:
        st.subheader("Mock Signal Lab")
        selected_symbol = st.selectbox("Filter symbol", ["All", "XAUUSD", "NAS100", "US30"])
        signals = _mock_signals()
        for signal in signals:
            if selected_symbol == "All" or signal["symbol"] == selected_symbol:
                _render_signal(signal)
        st.markdown("### Strategy Toggles")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.toggle("Liquidity sweeps", value=True)
            st.toggle("Order blocks", value=True)
        with s2:
            st.toggle("Fair value gaps", value=True)
            st.toggle("News filter", value=False)
        with s3:
            st.toggle("Session filter", value=True)
            st.toggle("Auto trade mock", value=False)

    with tab_journal:
        st.subheader("Trade Journal Preview")
        rows = []
        symbols = ["XAUUSD", "NAS100", "US30"]
        setups = ["FVG continuation", "Liquidity sweep", "Order block reaction", "BOS retest"]
        for i in range(8):
            risk = random.choice([75, 100, 125, 150, 200])
            r_mult = random.choice([-1, -0.5, 1.2, 1.8, 2.4, 3.0])
            rows.append(
                {
                    "Time": (datetime.now() - timedelta(hours=i * 3)).strftime("%m/%d %I:%M %p"),
                    "Symbol": random.choice(symbols),
                    "Setup": random.choice(setups),
                    "Result": f"{r_mult}R",
                    "P/L": _money(risk * r_mult),
                    "Notes": random.choice(["Clean entry", "Early exit", "News nearby", "Respected range", "Waited for close"]),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.text_area("Add session notes", placeholder="Example: London sweep gave cleaner entries than NY open today...")
        st.button("Save Mock Journal Note")


def render_accounts(role="client"):
    render_trading_accounts_page(role=role)


def render_frontend_accounts_page(role="client"):
    render_trading_accounts_page(role=role)


if __name__ == "__main__":
    st.set_page_config(page_title="Trading Accounts", page_icon="📈", layout="wide")
    render_trading_accounts_page("ceo")
