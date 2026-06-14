from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from agents.tradesmart_agent import TradeSmartAgent

SYMBOL = "XAUUSD"

# Easy throttle: change this number if you want the page/agent to check faster or slower.
TRADESMART_CHECK_INTERVAL_SECONDS = 3
TRADESMART_OUTPUT_LIMIT = 50
TRADESMART_WORKER_STATE_FILE = Path("data/tradesmart_worker_state.json")


def _save_tradesmart_worker_state(
    *,
    enabled: bool,
    mode: str,
    profile: Dict[str, Any],
    risk: Dict[str, Any],
    user_key: str,
) -> None:
    """Persist the TradeSmart run state for agents/tradesmart_worker.py."""
    TRADESMART_WORKER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(enabled),
        "mode": str(mode or "Demo"),
        "symbol": SYMBOL,
        "user_key": user_key,
        "profile": dict(profile or {}),
        "risk": dict(risk or {}),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    TRADESMART_WORKER_STATE_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")



def _inject_tradesmart_styles() -> None:
    st.markdown(
        """
        <style>
            .ts-hero {
                padding: 22px 24px;
                border-radius: 24px;
                background: linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.03));
                border: 1px solid rgba(255,255,255,.12);
                box-shadow: 0 18px 55px rgba(0,0,0,.22);
                margin-bottom: 18px;
                color: inherit;
            }

            .ts-title {
                font-size: 30px;
                font-weight: 900;
                color: inherit;
                margin: 0 0 8px 0;
                letter-spacing: -.02em;
            }

            .ts-muted {
                opacity: .72;
                font-size: 14px;
                line-height: 1.55;
                color: inherit;
            }

            .ts-section-title {
                padding: 15px 18px;
                border-radius: 20px;
                background: linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.025));
                border: 1px solid rgba(255,255,255,.11);
                box-shadow: 0 14px 42px rgba(0,0,0,.18);
                margin: 16px 0 12px 0;
                font-size: 16px;
                font-weight: 850;
                color: inherit;
            }

            .ts-pill {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                border-radius: 999px;
                padding: 8px 12px;
                border: 1px solid rgba(255,255,255,.13);
                background: rgba(255,255,255,.055);
                font-size: 12px;
                font-weight: 800;
                margin: 6px 0 8px 0;
                color: inherit;
            }

            .ts-dot {
                width: 8px;
                height: 8px;
                border-radius: 99px;
                background: #00ffa3;
                box-shadow: 0 0 18px rgba(0,255,163,.85);
            }

            .ts-spinner {
                width: 16px;
                height: 16px;
                border-radius: 999px;
                border: 2px solid rgba(255,255,255,.18);
                border-top-color: #00ffa3;
                animation: ts-spin .9s linear infinite;
                display: inline-block;
                vertical-align: middle;
                margin-right: 8px;
            }

            @keyframes ts-spin {
                to { transform: rotate(360deg); }
            }

            .ts-live-box {
                padding: 15px 16px;
                border-radius: 18px;
                background: rgba(0,255,163,.07);
                border: 1px solid rgba(0,255,163,.18);
                color: inherit;
                margin: 10px 0 12px 0;
            }

            .ts-live-head {
                font-weight: 900;
                margin-bottom: 6px;
                display: flex;
                align-items: center;
                color: inherit;
            }

            .ts-live-msg {
                opacity: .82;
                line-height: 1.45;
                font-size: 13px;
                color: inherit;
            }

            .ts-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 10px;
                margin: 10px 0 16px 0;
            }

            .ts-summary {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 10px;
                margin: 10px 0 16px 0;
            }

            .ts-metric {
                padding: 13px;
                border-radius: 16px;
                background: rgba(255,255,255,.045);
                border: 1px solid rgba(255,255,255,.09);
                min-height: 78px;
                color: inherit;
            }

            .ts-metric-label {
                opacity: .58;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: .08em;
                font-weight: 800;
                color: inherit;
            }

            .ts-metric-value {
                font-size: 18px;
                font-weight: 900;
                margin-top: 7px;
                color: inherit;
                word-break: break-word;
            }

            .ts-log-wrap {
                max-height: 320px;
                overflow-y: auto;
                padding: 10px;
                border-radius: 18px;
                background: linear-gradient(145deg, rgba(5,8,18,.96), rgba(12,18,34,.92)) !important;
                border: 1px solid rgba(255,255,255,.12) !important;
                color: rgba(255,255,255,.94) !important;
                box-shadow: inset 0 0 0 1px rgba(255,255,255,.035);
                color-scheme: dark;
                margin-bottom: 8px;
            }

            .ts-log-wrap * {
                color: rgba(255,255,255,.92) !important;
                color-scheme: dark;
            }

            .ts-log-wrap::-webkit-scrollbar {
                width: 8px;
            }

            .ts-log-wrap::-webkit-scrollbar-thumb {
                background: rgba(255,255,255,.22);
                border-radius: 99px;
            }

            .ts-log-item {
                padding: 12px 12px;
                border-radius: 14px;
                background: rgba(255,255,255,.07) !important;
                border: 1px solid rgba(255,255,255,.10) !important;
                margin-bottom: 8px;
            }

            .ts-log-title {
                font-weight: 900;
                font-size: 13px;
                margin-bottom: 5px;
            }

            .ts-log-msg {
                font-size: 13px;
                line-height: 1.35;
                opacity: .82;
            }

            @media (max-width: 900px) {
                .ts-grid, .ts-summary {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            @media (max-width: 560px) {
                .ts-grid, .ts-summary {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _section(title: str) -> None:
    st.markdown(f'<div class="ts-section-title">{escape(title)}</div>', unsafe_allow_html=True)


def _get_user_key() -> str:
    user = st.session_state.get("user")
    if isinstance(user, dict):
        for field in ("id", "token", "email", "username", "name", "role"):
            value = user.get(field)
            if value not in (None, ""):
                return f"user_{value}"
    return str(st.session_state.get("authenticated_user") or st.session_state.get("role") or "default")


def _load_mt5_profile(mode: str) -> Dict[str, Any]:
    """Load the exact Demo/Live profile saved in Settings using mt5_secure_store."""
    mode = str(mode or "Demo").title()
    try:
        import frontend.mt5_secure_store as store

        # Use the same key system as Settings. This is what keeps Dashboard and
        # TradeSmart reading the same encrypted saved MT5 profile.
        for role in ("client", "ceo"):
            try:
                user_key = store.get_signed_in_user_key(role)
                profile = store.load_mt5_profile(user_key, mode, role=role)
                if isinstance(profile, dict) and (
                    profile.get("login") or profile.get("password") or profile.get("server")
                ):
                    profile = dict(profile)
                    profile["mode"] = mode
                    return profile
            except Exception:
                continue

        # Store-level fallback for migrated/legacy keys.
        try:
            profile = store.load_mt5_profile("", mode, role="client")
            if isinstance(profile, dict) and (
                profile.get("login") or profile.get("password") or profile.get("server")
            ):
                profile = dict(profile)
                profile["mode"] = mode
                return profile
        except Exception:
            pass
    except Exception:
        pass

    return {}



def _masked_login(profile: Dict[str, Any]) -> str:
    login = str(profile.get("login") or "")
    return f"*{login[-4:]}" if login else "Not saved"


def _is_complete_profile(profile: Dict[str, Any]) -> bool:
    return bool(profile.get("login") and profile.get("password") and profile.get("server"))



def _strip_legacy_html(value: Any) -> str:
    """Prevent old saved HTML log/metric strings from rendering as visible markup."""
    text = str(value if value is not None else "")
    if "<" in text and ">" in text:
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</div\s*>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text


def _sanitize_existing_logs() -> None:
    logs = st.session_state.get("tradesmart_logs")
    if not isinstance(logs, list):
        st.session_state["tradesmart_logs"] = []
        return

    clean_logs = []
    for item in logs[:60]:
        if isinstance(item, dict):
            clean_logs.append(
                {
                    "time": _strip_legacy_html(item.get("time", "")),
                    "title": _strip_legacy_html(item.get("title", "Update")) or "Update",
                    "message": _strip_legacy_html(item.get("message", "")),
                    "balance": item.get("balance"),
                    "equity": item.get("equity"),
                }
            )
        else:
            clean_logs.append(
                {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "title": "Agent Update",
                    "message": _strip_legacy_html(item),
                    "balance": None,
                    "equity": None,
                }
            )
    st.session_state["tradesmart_logs"] = clean_logs

def _add_log(title: str, message: str, balance: Any = None, equity: Any = None) -> None:
    logs = st.session_state.setdefault("tradesmart_logs", [])
    logs.insert(
        0,
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": _strip_legacy_html(title),
            "message": _strip_legacy_html(message),
            "balance": balance,
            "equity": equity,
        },
    )
    del logs[TRADESMART_OUTPUT_LIMIT:]



def _render_logs() -> None:
    _sanitize_existing_logs()
    logs: List[Dict[str, Any]] = st.session_state.get("tradesmart_logs", [])

    def esc(value: Any) -> str:
        return escape(str(value if value is not None else "—"))

    if not logs:
        items_html = """
        <div class="log-item">
            <div class="log-title">TradeSmart Waiting</div>
            <div class="log-msg">Enable the agent after connecting MT5 to start live tracking.</div>
        </div>
        """
    else:
        parts = []
        for item in logs[:TRADESMART_OUTPUT_LIMIT]:
            balance = item.get("balance")
            equity = item.get("equity")
            meta = ""
            if balance is not None:
                meta = f'<div class="log-meta">Balance {esc(balance)} • Equity {esc(equity)}</div>'
            parts.append(
                f"""
                <div class="log-item">
                    <div class="log-title">{esc(item.get("title", "Update"))} <span>{esc(item.get("time", ""))}</span></div>
                    <div class="log-msg">{esc(item.get("message", ""))}</div>
                    {meta}
                </div>
                """
            )
        items_html = "".join(parts)

    html = f"""
    <!doctype html>
    <html>
    <head>
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background: transparent;
          font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: rgba(255,255,255,.94);
        }}
        .log-wrap {{
          height: 320px;
          overflow-y: auto;
          padding: 10px;
          border-radius: 18px;
          background: linear-gradient(145deg, rgba(5,8,18,.97), rgba(12,18,34,.94));
          border: 1px solid rgba(255,255,255,.13);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.035);
          box-sizing: border-box;
        }}
        .log-wrap::-webkit-scrollbar {{ width: 8px; }}
        .log-wrap::-webkit-scrollbar-thumb {{
          background: rgba(255,255,255,.24);
          border-radius: 99px;
        }}
        .log-item {{
          padding: 12px;
          border-radius: 14px;
          background: rgba(255,255,255,.075);
          border: 1px solid rgba(255,255,255,.10);
          margin-bottom: 8px;
        }}
        .log-title {{
          font-weight: 900;
          font-size: 13px;
          margin-bottom: 5px;
          color: rgba(255,255,255,.96);
        }}
        .log-title span {{
          opacity: .55;
          font-weight: 650;
          margin-left: 6px;
        }}
        .log-msg {{
          font-size: 13px;
          line-height: 1.38;
          color: rgba(255,255,255,.84);
        }}
        .log-meta {{
          margin-top: 5px;
          font-size: 12px;
          color: rgba(255,255,255,.62);
        }}
      </style>
    </head>
    <body>
      <div class="log-wrap">{items_html}</div>
    </body>
    </html>
    """
    components.html(html, height=350, scrolling=False)


def _render_metric_grid(items: List[tuple[str, Any]], summary: bool = False) -> None:
    cols_per_row = 3 if summary else 4
    for i in range(0, len(items), cols_per_row):
        row = items[i:i + cols_per_row]
        cols = st.columns(len(row))
        for col, (label, value) in zip(cols, row):
            with col:
                st.metric(str(label), str(value))

def _render_metrics(account: Optional[Dict[str, Any]], mode: str, connected: bool) -> None:
    account = account or {}
    _render_metric_grid(
        [
            ("Mode", mode),
            ("Symbol", SYMBOL),
            ("Connection", "Connected" if connected else "Disconnected"),
            ("Balance", account.get("balance", "—")),
            ("Equity", account.get("equity", "—")),
            ("Currency", account.get("currency", "—")),
            ("Open Trades", account.get("open_positions", "—")),
            ("Today P/L", account.get("daily_pl", "—")),
        ]
    )


def _render_summary(mode: str, profile: Dict[str, Any], agent_enabled: bool, risk: Dict[str, Any]) -> None:
    _render_metric_grid(
        [
            ("Mode", mode),
            ("Symbol", SYMBOL),
            ("Agent", "Enabled" if agent_enabled else "Idle"),
            ("Login", _masked_login(profile)),
            ("Server", profile.get("server") or "Not saved"),
            ("Volume", risk["trade_volume"]),
            ("Max Open Trades", risk["max_open_trades"]),
            ("Max Daily Loss", f"${risk['max_daily_loss_amount']:.2f}"),
            ("AI Rules", "Saved" if risk.get("ai_instructions") else "Empty"),
        ],
        summary=True,
    )



def _account_snapshot_key(user_key: str, mode: str) -> str:
    return f"tradesmart_account_snapshot_{user_key}_{mode}"


def _last_result_key(user_key: str, mode: str) -> str:
    return f"tradesmart_last_result_{user_key}_{mode}"


def _get_account_snapshot(user_key: str, mode: str) -> Dict[str, Any]:
    snapshot = st.session_state.get(_account_snapshot_key(user_key, mode), {})
    return snapshot if isinstance(snapshot, dict) else {}


def _set_account_snapshot(user_key: str, mode: str, account: Optional[Dict[str, Any]], result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account = dict(account or {})
    result = result or {}
    account["open_positions"] = result.get("open_positions_count", account.get("open_positions", 0))
    account["daily_pl"] = account.get("daily_pl", result.get("daily_pl", account.get("daily_pl", "—")))
    account["mode"] = mode
    account["symbol"] = SYMBOL
    account["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state[_account_snapshot_key(user_key, mode)] = account
    # Keep the old key synced for any existing code that still reads it.
    st.session_state["tradesmart_account_snapshot"] = account
    return account



def _connect_profile_for_tradesmart(profile: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """
    Use the same MT5 auto-login path as Dashboard/Settings for the initial
    TradeSmart connection. This avoids the Demo IPC issue caused by initializing
    MT5 through a different code path.
    """
    try:
        import frontend.mt5_secure_store as store

        profile = dict(profile or {})
        profile["mode"] = mode
        ok, message, account = store.connect_mt5(profile)
        positions = []
        if ok:
            try:
                positions = [
                    p for p in store.get_mt5_positions()
                    if str(p.get("symbol", "")).upper() == SYMBOL
                ]
            except Exception:
                positions = []

        return {
            "ok": bool(ok),
            "phase": "connect",
            "event": "Connected" if ok else "Connection Failed",
            "message": message,
            "thinking": message,
            "account": account or {},
            "open_positions_count": len(positions),
            "positions": positions,
        }
    except Exception as exc:
        return {
            "ok": False,
            "phase": "connect",
            "event": "Connection Failed",
            "message": f"MT5 auto-login failed: {exc}",
            "thinking": str(exc),
            "account": {},
            "open_positions_count": 0,
            "positions": [],
        }


def _refresh_account_snapshot(profile: Dict[str, Any], mode: str, user_key: str) -> Dict[str, Any]:
    agent = TradeSmartAgent(profile=profile, rules={"mode": mode, "symbol": SYMBOL})
    result = agent.snapshot_only()
    st.session_state[_last_result_key(user_key, mode)] = result
    if result.get("ok"):
        account = _set_account_snapshot(user_key, mode, result.get("account"), result)
        positions = result.get("positions") or []
        if positions:
            tracked = []
            for pos in positions[:5]:
                p_type = int(pos.get("type", 0) or 0)
                direction = "BUY" if p_type == 0 else "SELL"
                tracked.append(f"{direction} ticket {pos.get('ticket')} profit {pos.get('profit')}")
            _add_log("Live Refresh", "Updated selected account. " + " | ".join(tracked), account.get("balance"), account.get("equity"))
        return account

    _add_log("Refresh Failed", result.get("message", "Could not refresh selected MT5 account."))
    return _get_account_snapshot(user_key, mode)



def _run_agent_cycle(profile: Dict[str, Any], mode: str, risk: Dict[str, Any], execution_enabled: bool, user_key: str) -> Dict[str, Any]:
    agent = TradeSmartAgent(profile=profile, rules={**risk, "mode": mode, "symbol": SYMBOL})
    result = agent.run_cycle(execution_enabled=execution_enabled)

    st.session_state["tradesmart_last_result"] = result
    st.session_state[_last_result_key(user_key, mode)] = result

    # Hard stop persistence: if the agent hits the max-loss lock, immediately
    # write disabled state to the worker file so the background worker cannot
    # keep running while the Streamlit UI reruns. The UI toggle is also forced
    # off below, so the user must manually turn it back on.
    if result.get("max_daily_loss_reached"):
        _save_tradesmart_worker_state(
            enabled=False,
            mode=mode,
            profile=profile,
            risk=risk,
            user_key=user_key,
        )

    account = _set_account_snapshot(user_key, mode, result.get("account") or {}, result)

    decision = result.get("decision") or {}
    action = str(decision.get("action", "NONE")).upper()
    strategy = result.get("strategy") or "strategy core"
    positions = result.get("positions") or []
    order_result = result.get("order_result") or {}

    title = str(result.get("event", result.get("phase", "Agent Update"))).replace("_", " ").title()
    message_parts = []

    main_message = _strip_legacy_html(result.get("message", "TradeSmart checked the market."))
    thinking = _strip_legacy_html(result.get("thinking", ""))
    if main_message:
        message_parts.append(main_message)
    if thinking and thinking != main_message:
        message_parts.append(thinking)

    if action and action != "NONE":
        message_parts.append(f"Decision: {action} {SYMBOL}")

    if result.get("order_sent"):
        message_parts.append("Execution: order accepted by MT5.")
    elif order_result and isinstance(order_result, dict) and order_result.get("message"):
        message_parts.append(f"Execution: {_strip_legacy_html(order_result.get('message'))}")

    if positions:
        tracked = []
        for pos in positions[:5]:
            p_type = int(pos.get("type", 0) or 0)
            direction = "BUY" if p_type == 0 else "SELL"
            tracked.append(
                f"{direction} ticket {pos.get('ticket')} volume {pos.get('volume')} profit {pos.get('profit')}"
            )
        message_parts.append("Tracking: " + " | ".join(tracked))

    message = " — ".join([p for p in message_parts if p])
    _add_log(title, message, account.get("balance"), account.get("equity"))
    return result



def _render_live_output(result: Dict[str, Any]) -> None:
    try:
        from agents.outputs import build_live_thinking_html
        html = str(build_live_thinking_html(result))
    except Exception:
        decision = result.get("decision") or {}
        action = escape(str(decision.get("action", "NONE")))
        msg = escape(str(result.get("thinking") or result.get("message") or "Checking XAUUSD."))
        html = f"""
        <!doctype html>
        <html>
        <head>
          <style>
            html, body {{
              margin: 0;
              padding: 0;
              background: transparent;
              font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              color: rgba(255,255,255,.94);
            }}
            .box {{
              padding: 14px 16px;
              border-radius: 18px;
              background: rgba(0,255,163,.075);
              border: 1px solid rgba(0,255,163,.20);
              box-sizing: border-box;
            }}
            .head {{ font-weight: 900; display: flex; align-items: center; margin-bottom: 6px; }}
            .spin {{
              width: 16px; height: 16px; border-radius: 50%;
              border: 2px solid rgba(255,255,255,.18);
              border-top-color: #00ffa3;
              animation: spin .9s linear infinite;
              display:inline-block; margin-right: 8px;
            }}
            .msg {{ font-size: 13px; line-height: 1.4; color: rgba(255,255,255,.84); }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
          </style>
        </head>
        <body>
          <div class="box">
            <div class="head"><span class="spin"></span>TradeSmart Thinking</div>
            <div class="msg">{msg}</div>
            <div class="msg" style="opacity:.72;">Direction: {action}</div>
          </div>
        </body>
        </html>
        """
    components.html(html, height=150, scrolling=False)

def render_tradesmart(role: str = "client") -> None:
    _sanitize_existing_logs()
    _inject_tradesmart_styles()
    user_key = _get_user_key()
    force_stop_key = f"tradesmart_force_stop_{user_key}"
    loss_msg_key = f"tradesmart_loss_msg_{user_key}"

    st.markdown(
        """
        <div class="ts-hero">
            <div class="ts-title">TradeSmart</div>
            <div class="ts-muted">
                TradeSmart is your Dropzuniversal AI trading sub-agent for auto-trade monitoring,
                risk setup, smart entries, exits, portfolio rules, and strategy automation.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _section("MT5 TradeSmart Connection")

    connected_key = f"tradesmart_connected_{user_key}"
    connected_mode_key = f"tradesmart_connected_mode_{user_key}"
    active_connected_mode = st.session_state.get(connected_mode_key)
    connected_now = bool(st.session_state.get(connected_key)) and active_connected_mode in ("Demo", "Live")

    mode_key = f"tradesmart_mode_{user_key}"
    if connected_now:
        # Lock Demo/Live while connected. Users must disconnect before switching.
        st.session_state[mode_key] = active_connected_mode

    mode = st.radio(
        "TradeSmart MT5 Mode",
        ["Demo", "Live"],
        horizontal=True,
        key=mode_key,
        disabled=connected_now,
        index=0 if st.session_state.get(mode_key, "Demo") != "Live" else 1,
    )

    if connected_now:
        mode = active_connected_mode
        st.info(f"{active_connected_mode} is currently connected. Disconnect before switching Demo/Live mode.")

    profile = _load_mt5_profile(mode)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Selected Mode", mode)
    with c2:
        st.metric("Saved Login", _masked_login(profile))
    with c3:
        st.metric("Server", profile.get("server") or "Not saved")

    if _is_complete_profile(profile):
        st.success(f"{mode} MT5 credentials are loaded for this signed-in user.")
    else:
        st.warning(f"{mode} MT5 credentials are not complete yet. Go to Settings and save MT5 Login, Password, and Server.")

    connected = bool(st.session_state.get(connected_key)) and active_connected_mode == mode

    b1, b2 = st.columns([1, 1])
    with b1:
        if not connected:
            if st.button(f"Connect {mode} MT5", use_container_width=True, disabled=not _is_complete_profile(profile)):
                result = _connect_profile_for_tradesmart(profile, mode)
                if result.get("ok"):
                    st.session_state[connected_key] = True
                    st.session_state[connected_mode_key] = mode
                    _set_account_snapshot(user_key, mode, result.get("account", {}), result)
                    _add_log("Connected", result.get("message", f"Connected to {mode} MT5."), result.get("account", {}).get("balance"), result.get("account", {}).get("equity"))
                    st.rerun()
                else:
                    _add_log("Connection Failed", result.get("message", "MT5 connection failed."))
                    st.error(result.get("message", "MT5 connection failed."))
        else:
            if st.button(f"Disconnect {mode} MT5", use_container_width=True):
                # One last fresh snapshot before disconnect keeps the page from
                # showing an old open-trade count after the agent is stopped.
                if _is_complete_profile(profile):
                    _refresh_account_snapshot(profile, mode, user_key)
                TradeSmartAgent(profile=profile, rules={"mode": mode, "symbol": SYMBOL}).disconnect()
                st.session_state[connected_key] = False
                st.session_state[connected_mode_key] = None
                _save_tradesmart_worker_state(
                    enabled=False,
                    mode=mode,
                    profile=profile,
                    risk={},
                    user_key=user_key,
                )
                _add_log("Disconnected", f"Disconnected from {mode} MT5.")
                st.rerun()

    with b2:
        st.markdown(
            f"""
            <div class="ts-pill"><span class="ts-dot"></span>{'Connected' if connected else 'Disconnected'} • {escape(mode)} • {SYMBOL}</div>
            """,
            unsafe_allow_html=True,
        )

    agent_key = f"enable_tradesmart_agent_{user_key}_{mode}"
    if st.session_state.pop(force_stop_key, False):
        st.session_state[agent_key] = False
        _save_tradesmart_worker_state(
            enabled=False,
            mode=mode,
            profile=profile,
            risk={},
            user_key=user_key,
        )

    _section("AI Trading Agent Status")
    agent_enabled = st.toggle("Enable TradeSmart Agent", value=False, key=agent_key)

    loss_msg = st.session_state.pop(loss_msg_key, None)
    if loss_msg:
        st.error(loss_msg)

    if agent_enabled and connected:
        st.markdown(
            """
            <div class="ts-live-box">
                <div class="ts-live-head"><span class="ts-spinner"></span>Agent running</div>
                <div class="ts-live-msg">Checking XAUUSD every 3 seconds. The agent reads strategies, opens valid setups, tracks open trades, and closes by strategy/risk rules.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif agent_enabled and not connected:
        st.info("Connect MT5 before enabling live TradeSmart tracking.")
    else:
        st.info(f"TradeSmart Agent is idle in {mode} mode.")

    _section("Risk Parameters")
    r1, r2, r3 = st.columns(3)
    with r1:
        trade_volume = st.number_input("Trade Volume", min_value=0.01, max_value=100.0, value=0.01, step=0.01, format="%.2f", key=f"ts_vol_{user_key}")
    with r2:
        max_open_trades = st.number_input("Max Open Trades", min_value=1, max_value=20, value=1, step=1, key=f"ts_max_open_{user_key}")
    with r3:
        max_daily_loss_amount = st.number_input("Max Daily Loss Amount", min_value=0.0, max_value=100000.0, value=1.00, step=0.50, format="%.2f", key=f"ts_max_loss_{user_key}")

    st.caption("Max Daily Loss Amount is a hard kill-switch. If one tracked trade, all tracked trades combined, or account equity drawdown reaches this amount, TradeSmart closes tracked trades, turns the agent off, and requires you to turn it back on manually.")

    _section("AI Agent Instructions")
    ai_instructions = st.text_area(
        "Custom TradeSmart Agent Rules",
        placeholder="Example: Avoid entries during major news, favor cleaner momentum candles, and keep risk tight.",
        height=120,
        key=f"tradesmart_ai_instructions_{user_key}",
    )

    risk = {
        "trade_volume": float(trade_volume),
        "max_open_trades": int(max_open_trades),
        "max_daily_loss_amount": float(max_daily_loss_amount),
        "ai_instructions": ai_instructions,
        "allow_live_execution": mode == "Live",
        "entry_cooldown_seconds": 60,
        "check_interval_seconds": TRADESMART_CHECK_INTERVAL_SECONDS,
    }

    _save_tradesmart_worker_state(
        enabled=bool(agent_enabled and connected),
        mode=mode,
        profile=profile,
        risk=risk,
        user_key=user_key,
    )

    _section("Live Trade Tracking")

    if connected and agent_enabled:
        @st.fragment(run_every=TRADESMART_CHECK_INTERVAL_SECONDS)
        def _live_cycle() -> None:

            result = _run_agent_cycle(
                profile,
                mode,
                risk,
                execution_enabled=True,
                user_key=user_key,
            )

            account = _get_account_snapshot(user_key, mode)
            _render_metrics(account, mode, True)
            _render_live_output(result)

            if result.get("max_daily_loss_reached"):
                st.session_state[force_stop_key] = True
                st.session_state[loss_msg_key] = result.get(
                    "message",
                    "Max daily loss limit reached. Agent stopped.",
                )
                st.error(st.session_state[loss_msg_key])
                st.rerun()

        _live_cycle()
    elif connected:
        @st.fragment(run_every=TRADESMART_CHECK_INTERVAL_SECONDS)
        def _snapshot_cycle() -> None:
            account = _refresh_account_snapshot(profile, mode, user_key)
            _render_metrics(account, mode, True)

        _snapshot_cycle()
    else:
        account = _get_account_snapshot(user_key, mode)
        _render_metrics(account, mode, connected)

    _section("TradeSmart Configuration Summary")
    _render_summary(mode, profile, agent_enabled, risk)

    _section("TradeSmart Agent Output")
    if connected and agent_enabled:
        @st.fragment(run_every=TRADESMART_CHECK_INTERVAL_SECONDS)
        def _live_logs_cycle() -> None:
            _render_logs()

        _live_logs_cycle()
    else:
        _render_logs()


def render_frontend_tradesmart_page(role: str = "client"):
    render_tradesmart(role)
    return None
