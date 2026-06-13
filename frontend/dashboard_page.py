from __future__ import annotations

import streamlit as st

from components.dashboard_mt5_data import get_live_mt5_dashboard_data
from components.dashboard_quotes import get_daily_session_quote
from components.kpi_cards import render_kpi_cards
from components.tables import render_last_10_trades
from components.activity_feed import render_activity_feed
from components.charts import render_performance_charts


# ── styles ───────────────────────────────────────────────────────────────────

def _inject_dashboard_styles():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
.stApp, .du-dashboard-hero, .du-card, .du-kpi-card { font-family:'Inter',sans-serif !important; }

/* ── hero ─────────────────────────────────────────────────────────────── */
.du-dashboard-hero{
    padding:28px 30px;border-radius:26px;position:relative;overflow:hidden;
    background:linear-gradient(135deg,rgba(0,255,163,.08),rgba(255,255,255,.025) 55%);
    border:1px solid rgba(255,255,255,.12);
    box-shadow:0 18px 60px rgba(0,0,0,.30);
    margin-bottom:18px;
}
.du-dashboard-hero::after{
    content:"";position:absolute;top:-60%;right:-10%;width:340px;height:340px;
    background:radial-gradient(circle,rgba(0,255,163,.16),transparent 70%);
    pointer-events:none;
}
.du-dashboard-title{font-size:32px;font-weight:900;color:#fff;margin-bottom:4px;letter-spacing:-.01em}
.du-dashboard-sub{color:rgba(255,255,255,.62);font-size:14.5px}

/* ── generic cards ────────────────────────────────────────────────────── */
.du-card{
    padding:22px;border-radius:22px;
    background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.025));
    border:1px solid rgba(255,255,255,.10);
    box-shadow:0 16px 46px rgba(0,0,0,.24);
    margin-bottom:18px;
}

/* ── KPI cards ────────────────────────────────────────────────────────── */
.du-kpi-card{
    padding:18px 20px;border-radius:20px;
    background:linear-gradient(145deg,rgba(255,255,255,.085),rgba(255,255,255,.03));
    border:1px solid rgba(255,255,255,.105);
    box-shadow:0 14px 38px rgba(0,0,0,.20);
    min-height:128px;transition:transform .2s ease, box-shadow .2s ease;
}
.du-kpi-card:hover{transform:translateY(-3px);box-shadow:0 18px 46px rgba(0,0,0,.30)}
.du-kpi-top{display:flex;align-items:center;gap:8px;margin-bottom:2px}
.du-kpi-icon{font-size:16px;line-height:1}
.du-kpi-label{color:rgba(255,255,255,.55);font-size:12px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;flex:1}
.du-kpi-trend{font-size:11px;font-weight:900;padding:2px 7px;border-radius:999px}
.du-kpi-value{color:#fff;font-size:25px;font-weight:900;margin-top:10px}
.du-kpi-unit{font-size:13px;font-weight:700;color:rgba(255,255,255,.45)}
.du-kpi-sub{color:rgba(255,255,255,.50);font-size:11.5px;margin-top:8px}
.du-trend-up{color:#00ffa3;background:rgba(0,255,163,.12)}
.du-trend-down{color:#ff6b88;background:rgba(255,107,136,.12)}
.du-trend-flat{color:rgba(255,255,255,.5);background:rgba(255,255,255,.06)}
.du-kpi-value.du-trend-up{color:#00ffa3}
.du-kpi-value.du-trend-down{color:#ff6b88}
.du-kpi-progress-track{height:6px;border-radius:999px;background:rgba(255,255,255,.08);margin-top:10px;overflow:hidden}
.du-kpi-progress-fill{height:100%;border-radius:999px;transition:width .4s ease}

/* ── quote card ───────────────────────────────────────────────────────── */
.du-quote{padding:22px 24px;border-radius:24px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);margin-bottom:18px}
.du-quote-good{box-shadow:0 0 35px rgba(0,255,163,.16);border-color:rgba(0,255,163,.28)}
.du-quote-bad{box-shadow:0 0 35px rgba(255,77,109,.18);border-color:rgba(255,77,109,.30)}
.du-quote-label{color:rgba(255,255,255,.52);font-size:11.5px;text-transform:uppercase;letter-spacing:1.4px;font-weight:900;margin-bottom:8px}
.du-quote-text{color:#fff;font-size:17px;font-weight:700;line-height:1.5}

/* ── account mini grid ───────────────────────────────────────────────── */
.du-mini-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.du-mini{padding:14px;border-radius:16px;background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.08);transition:border-color .2s ease}
.du-mini:hover{border-color:rgba(255,255,255,.18)}
.du-mini-label{color:rgba(255,255,255,.52);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;display:flex;align-items:center;gap:6px}
.du-mini-value{color:#fff;font-size:18px;font-weight:900;margin-top:6px}
.du-status-online{color:#00ffa3}
.du-status-offline{color:#ff6b88}
.du-positive{color:#00ffa3}
.du-negative{color:#ff6b88}

/* ── section headers ──────────────────────────────────────────────────── */
.du-section-head{display:flex;align-items:center;gap:9px;margin:2px 0 12px}
.du-section-icon{font-size:18px;line-height:1}
.du-section-title-text{font-size:17px;font-weight:800;color:#fff}

/* ── empty state ──────────────────────────────────────────────────────── */
.du-empty-state{padding:40px 20px;text-align:center;border-radius:18px;background:rgba(0,0,0,.16);border:1px dashed rgba(255,255,255,.12)}
.du-empty-icon{font-size:32px;margin-bottom:10px}
.du-empty-title{color:rgba(255,255,255,.85);font-weight:800;font-size:15px;margin-bottom:4px}
.du-empty-sub{color:rgba(255,255,255,.48);font-size:13px}

/* ── activity feed ────────────────────────────────────────────────────── */
.du-activity-item{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-bottom:1px solid rgba(255,255,255,.08)}
.du-activity-item:last-child{border-bottom:none}
.du-activity-icon{font-size:17px;line-height:1.4;flex-shrink:0}
.du-activity-title{color:rgba(255,255,255,.88);font-size:13px;font-weight:700}
.du-activity-sub{font-size:12.5px;margin-top:2px;color:rgba(255,255,255,.62)}
.du-activity-meta{color:rgba(255,255,255,.40);font-weight:500}
.du-feed-positive{color:#00ffa3}
.du-feed-negative{color:#ff6b88}
.du-feed-neutral{color:rgba(255,255,255,.65)}

/* ── account mode selector ────────────────────────────────────────────── */
.du-mode-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:14px}
.du-mode-pill{
    display:inline-flex;align-items:center;gap:7px;padding:6px 14px;border-radius:999px;
    font-size:12.5px;font-weight:800;letter-spacing:.4px;
    border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.20);color:rgba(255,255,255,.7);
}
.du-mode-pill.online{border-color:rgba(0,255,163,.35);color:#00ffa3;background:rgba(0,255,163,.08)}
.du-mode-pill.offline{border-color:rgba(255,107,136,.35);color:#ff6b88;background:rgba(255,107,136,.08)}
.du-mode-dot{width:8px;height:8px;border-radius:999px;background:currentColor;box-shadow:0 0 8px currentColor}

/* radio pills override for account mode selector */
div[data-testid="stRadio"] > div[role="radiogroup"]{
    gap:6px !important;background:rgba(0,0,0,.18);padding:5px;border-radius:14px;
    border:1px solid rgba(255,255,255,.08);display:inline-flex;
}
div[data-testid="stRadio"] label{
    border-radius:10px !important;padding:6px 16px !important;margin:0 !important;
    transition:background .15s ease, color .15s ease;
}
div[data-testid="stRadio"] label:has(input:checked){
    background:linear-gradient(135deg,#00ffa3,#00c98a) !important;
}
div[data-testid="stRadio"] label:has(input:checked) p{
    color:#04130c !important;font-weight:800 !important;
}
div[data-testid="stRadio"] label p{
    color:rgba(255,255,255,.65) !important;font-weight:700 !important;font-size:13px !important;
}

/* refresh button */
div[data-testid="stButton"] button{
    border-radius:12px !important;font-weight:800 !important;font-size:13px !important;
    background:rgba(255,255,255,.06) !important;border:1px solid rgba(255,255,255,.14) !important;
    color:rgba(255,255,255,.85) !important;
}
div[data-testid="stButton"] button:hover{
    border-color:rgba(0,255,163,.40) !important;color:#00ffa3 !important;
}

/* stability / anti-overlap polish */
.du-card,.du-kpi-card,.du-dashboard-hero,.du-quote,.du-mini{box-sizing:border-box;max-width:100%;}
.du-mini-value,.du-quote-text,.du-activity-sub{overflow-wrap:anywhere;word-break:break-word;}
[data-testid="stDataFrame"]{border-radius:18px;overflow:hidden;border:1px solid rgba(255,255,255,.10);}
.block-container{padding-top:1.25rem;}
@media (max-width: 900px){
    .du-dashboard-hero{padding:22px 18px;border-radius:22px;}
    .du-dashboard-title{font-size:26px;}
    .du-mini-grid{grid-template-columns:1fr;}
    .du-kpi-card{min-height:auto;margin-bottom:10px;}
    .du-mode-pill{width:100%;justify-content:center;white-space:normal;text-align:center;}
    div[data-testid="stRadio"] > div[role="radiogroup"]{width:100%;display:flex;flex-wrap:wrap;}
    div[data-testid="stRadio"] label{flex:1;justify-content:center;}
}
</style>""", unsafe_allow_html=True)


# ── account / mode helpers ─────────────────────────────────────────────────

def _switch_account_mode(role: str, user_key: str, new_mode: str) -> None:
    """
    Persist the chosen Demo/Live mode if the secure store supports it,
    and always set a session override so the dashboard reflects the
    chosen mode immediately on this run.
    """
    try:
        from frontend.mt5_secure_store import set_active_mt5_mode
        set_active_mt5_mode(user_key, new_mode)
    except Exception:
        pass
    st.session_state["dashboard_mt5_mode_override"] = new_mode


def _ensure_dashboard_mt5_session(role=None, *, connect: bool = False):
    """Prepare the selected Demo/Live profile without freezing the dashboard.

    connect=False is the default for normal dashboard renders. It only loads
    saved profile metadata, so Streamlit does not start MT5 or freeze while
    loading the page. connect=True is used only from the manual button.
    """
    try:
        from frontend.mt5_secure_store import (
            get_signed_in_user_key,
            get_active_mt5_mode,
            load_mt5_profile,
            is_profile_ready,
            connect_mt5,
        )
        current_role = role or "client"
        user_key = get_signed_in_user_key(current_role)

        mode = st.session_state.get("dashboard_mt5_mode_override") or get_active_mt5_mode(user_key, role=current_role)
        mode = str(mode or "Demo").strip().title()
        if mode not in {"Demo", "Live"}:
            mode = "Demo"

        st.session_state["dashboard_mt5_user_key"] = user_key
        st.session_state["dashboard_mt5_role"] = current_role
        st.session_state["dashboard_mt5_mode"] = mode.lower()

        profile = load_mt5_profile(user_key, mode, role=current_role)
        ready, missing = is_profile_ready(profile)
        st.session_state["dashboard_mt5_ready"] = bool(ready)
        st.session_state["dashboard_mt5_ready_reason"] = missing if not ready else []

        if not ready:
            st.session_state["dashboard_mt5_auto_connected"] = False
            st.session_state["dashboard_mt5_message"] = (
                "Missing saved MT5 fields: " + ", ".join(missing) if missing else f"No saved {mode} credentials yet."
            )
            st.session_state.pop("dashboard_mt5_account", None)
            return

        if not connect:
            st.session_state.setdefault("dashboard_mt5_auto_connected", False)
            st.session_state.setdefault("dashboard_mt5_message", f"{mode} profile is ready. Press Connect / Read Account to refresh live data.")
            return

        connected, message, account = connect_mt5(profile)
        st.session_state["dashboard_mt5_auto_connected"] = bool(connected)
        st.session_state["dashboard_mt5_message"] = message
        if account:
            st.session_state["dashboard_mt5_account"] = account
        elif not connected:
            st.session_state.pop("dashboard_mt5_account", None)

    except Exception as exc:
        st.session_state["dashboard_mt5_auto_connected"] = False
        st.session_state["dashboard_mt5_message"] = str(exc)
        st.session_state.setdefault("dashboard_mt5_mode", "demo")
        st.session_state.setdefault("dashboard_mt5_ready", False)


def _render_mode_selector(role=None):
    """
    Demo / Live account selector + connection status + manual refresh.
    Lets the user pick which saved MT5 profile the dashboard should read
    from, without ever needing the MT5 terminal open manually.
    """
    current_mode = str(st.session_state.get("dashboard_mt5_mode", "demo")).strip().lower()
    options = ["demo", "live"]
    labels = {"demo": "🧪 Demo Account", "live": "🔴 Live Account"}

    sel_col, status_col, refresh_col = st.columns([2.4, 3.2, 1])

    with sel_col:
        choice = st.radio(
            "Account mode",
            options=options,
            index=options.index(current_mode) if current_mode in options else 0,
            format_func=lambda v: labels.get(v, v.title()),
            horizontal=True,
            label_visibility="collapsed",
            key="du_mode_radio",
        )

    if choice != current_mode:
        user_key = st.session_state.get("dashboard_mt5_user_key", "")
        _switch_account_mode(role or "client", user_key, choice)
        _ensure_dashboard_mt5_session(role, connect=False)
        st.rerun()

    connected = bool(st.session_state.get("dashboard_mt5_auto_connected"))
    message = st.session_state.get("dashboard_mt5_message", "")
    ready = bool(st.session_state.get("dashboard_mt5_ready"))

    with status_col:
        if connected:
            pill = (
                '<span class="du-mode-pill online">'
                '<span class="du-mode-dot"></span>'
                f'Connected · {labels.get(current_mode, current_mode.title())}'
                '</span>'
            )
        elif ready:
            pill = (
                '<span class="du-mode-pill offline">'
                '<span class="du-mode-dot"></span>'
                f'{labels.get(current_mode, current_mode.title())} selected · ready to read'
                + (f' — {message}' if message else '')
                + '</span>'
            )
        else:
            pill = (
                '<span class="du-mode-pill offline">'
                '<span class="du-mode-dot"></span>'
                f'No {labels.get(current_mode, current_mode.title())} credentials saved — add them in Settings'
                '</span>'
            )
        st.markdown(f'<div class="du-mode-row">{pill}</div>', unsafe_allow_html=True)

    with refresh_col:
        if st.button("🔌 Connect / Read", use_container_width=True, key="du_refresh_btn"):
            _ensure_dashboard_mt5_session(role, connect=True)
            st.rerun()


# ── render helpers ───────────────────────────────────────────────────────────

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
    open_profit = float(metrics.get("open_profit", 0) or 0)
    open_profit_cls = "du-positive" if open_profit >= 0 else "du-negative"

    mode = str(st.session_state.get("dashboard_mt5_mode", "demo")).strip().lower()
    mode_badge = "🧪 Demo" if mode == "demo" else "🔴 Live"

    st.markdown(
        '<div class="du-section-head">'
        '<span class="du-section-icon">🖥️</span>'
        f'<span class="du-section-title-text">MT5 Account — {mode_badge}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="du-card">
            <div class="du-mini-grid">
                <div class="du-mini"><div class="du-mini-label">🔌 Status</div><div class="du-mini-value {status_class}">{status}</div></div>
                <div class="du-mini"><div class="du-mini-label">🥇 Symbol</div><div class="du-mini-value">{symbol}</div></div>
                <div class="du-mini"><div class="du-mini-label">💰 Balance</div><div class="du-mini-value">{balance:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">📊 Equity</div><div class="du-mini-value">{equity:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">📂 Open Trades</div><div class="du-mini-value">{open_positions}</div></div>
                <div class="du-mini"><div class="du-mini-label">⚡ Open P/L</div><div class="du-mini-value {open_profit_cls}">{open_profit:,.2f} {currency}</div></div>
                <div class="du-mini"><div class="du-mini-label">🪪 Account</div><div class="du-mini-value">{login}</div></div>
                <div class="du-mini"><div class="du-mini-label">🌐 Server</div><div class="du-mini-value">{server}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_quote(data):
    quote = get_daily_session_quote(data.get("metrics", {}))
    st.markdown(
        f'<div class="du-quote {quote["glow_class"]}">'
        f'<div class="du-quote-label">Session Quote</div>'
        f'<div class="du-quote-text">{quote["quote"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── main entry ────────────────────────────────────────────────────────────────

def render_frontend_dashboard_page(role=None):
    _inject_dashboard_styles()

    # Load selected Demo/Live profile metadata only. Do not auto-start MT5 on page load.
    _ensure_dashboard_mt5_session(role, connect=False)

    mode = str(st.session_state.get("dashboard_mt5_mode", "demo")).strip().lower()
    mode_label = "Demo" if mode == "demo" else "Live"
    data = get_live_mt5_dashboard_data("XAUUSD", mode_label=mode_label)

    st.markdown(
        '<div class="du-dashboard-hero">'
        '<div class="du-dashboard-title">⚡ Trading Intelligence</div>'
        '<div class="du-dashboard-sub">Live XAUUSD trade log, account performance, and progress feedback.</div>',
        unsafe_allow_html=True,
    )
    _render_mode_selector(role)
    st.markdown('</div>', unsafe_allow_html=True)

    if data.get("error"):
        st.markdown(
            f'<div class="du-mode-row" style="margin-bottom:14px">'
            f'<span class="du-mode-pill offline"><span class="du-mode-dot"></span>'
            f'MT5 read error: {data["error"]}</span></div>',
            unsafe_allow_html=True,
        )

    _render_quote(data)
    render_kpi_cards(data)

    left, right = st.columns([2, 1])

    with left:
        render_last_10_trades(data.get("last_10_trades", []))
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="du-section-head">'
            '<span class="du-section-icon">📊</span>'
            '<span class="du-section-title-text">Performance Console</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        render_performance_charts(data)

    with right:
        _render_live_account(data)
        st.markdown('<div class="du-card">', unsafe_allow_html=True)
        render_activity_feed(data)
        st.markdown('</div>', unsafe_allow_html=True)
