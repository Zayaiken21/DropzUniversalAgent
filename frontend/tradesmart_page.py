from __future__ import annotations

from datetime import datetime
import hashlib
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, Tuple
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from agents.tradesmart_agent import TradeSmartAgent
from agents.tradesmart_worker import write_draw_commands
from agents.outputs import build_live_thinking_html

SYMBOL              = "XAUUSD"
REFRESH_ON_SECONDS  = 3     # fragment refresh when agent is ON
MARKET_TZ           = ZoneInfo("America/New_York")


# ══════════════════════════════════════════════
#  PATHS / CSS
# ══════════════════════════════════════════════

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _inject_css() -> None:
    for css_path in (
        _project_root() / "styles" / "tradesmart_page.css",
        _project_root() / "styles" / "TradeSmartpage.css",
    ):
        if css_path.exists():
            st.markdown(
                f"<style>{css_path.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True,
            )
            return


def _section(title: str) -> None:
    st.markdown(
        f'<div class="ts-section-title">{escape(title)}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════
#  USER / SCOPE HELPERS  (no user display name exposed)
# ══════════════════════════════════════════════

def _user_key() -> str:
    user = st.session_state.get("user")
    if isinstance(user, dict):
        for key in ("id", "email", "username", "token", "name", "role"):
            if user.get(key):
                return f"user_{user[key]}"
    return str(
        st.session_state.get("authenticated_user")
        or st.session_state.get("role")
        or "default"
    )


def _safe_user_id(value: Any) -> str:
    raw   = str(value or "default")
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")[:64]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{clean or 'user'}_{digest}"


def _set_scope(user_key: str, mode: str) -> None:
    st.session_state["_tradesmart_scope_user"]    = user_key
    st.session_state["_tradesmart_scope_user_id"] = _safe_user_id(user_key)
    st.session_state["_tradesmart_scope_mode"]    = str(mode or "Demo").title()


def _scope_key(name: str, user_key: str | None = None, mode: str | None = None) -> str:
    user_id   = _safe_user_id(user_key or st.session_state.get("_tradesmart_scope_user") or _user_key())
    mode_text = str(mode or st.session_state.get("_tradesmart_scope_mode") or "Demo").title()
    return f"{name}_{user_id}_{mode_text}"


# ══════════════════════════════════════════════
#  MT5 PROFILE
# ══════════════════════════════════════════════

def _load_mt5_profile(mode: str) -> Dict[str, Any]:
    mode = str(mode or "Demo").title()
    try:
        import frontend.mt5_secure_store as store
        for role in ("client", "ceo"):
            try:
                key     = store.get_signed_in_user_key(role)
                profile = store.load_mt5_profile(key, mode, role=role)
                if isinstance(profile, dict) and (
                    profile.get("login") or profile.get("password") or profile.get("server")
                ):
                    out       = dict(profile)
                    out["mode"] = mode
                    return out
            except Exception:
                continue
    except Exception:
        pass
    return {}


def _complete_profile(profile: Dict[str, Any]) -> bool:
    return bool(
        profile.get("login") and profile.get("password") and profile.get("server")
    )


def _masked_login(profile: Dict[str, Any]) -> str:
    login = str(profile.get("login") or "")
    return f"*{login[-4:]}" if login else "Not saved"


# ══════════════════════════════════════════════
#  MARKET STATUS
# ══════════════════════════════════════════════

def _market_status(now: datetime | None = None) -> Tuple[bool, str, datetime]:
    et   = (now or datetime.now(tz=MARKET_TZ)).astimezone(MARKET_TZ)
    wd   = et.weekday()
    mins = et.hour * 60 + et.minute
    if wd == 5:
        return False, "Weekend closure. Gold reopens Sunday 6:00 PM Eastern.", et
    if wd == 6 and mins < 18 * 60:
        return False, "Weekend closure. Gold reopens Sunday 6:00 PM Eastern.", et
    if wd == 4 and mins >= 17 * 60:
        return False, "Friday closure after 5:00 PM Eastern.", et
    if 17 * 60 <= mins < 18 * 60:
        return False, "Daily gold rollover 5–6 PM Eastern.", et
    return True, "Market open.", et


# ══════════════════════════════════════════════
#  LOG HELPERS
# ══════════════════════════════════════════════

def _add_log(title: str, message: str, result: Dict[str, Any] | None = None) -> None:
    log_key = _scope_key("tradesmart_logs")
    logs    = st.session_state.setdefault(log_key, [])
    account = (result or {}).get("account") or {}
    logs.insert(0, {
        "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title":   str(title),
        "message": str(message),
        "balance": account.get("balance"),
        "equity":  account.get("equity"),
    })
    st.session_state[log_key] = logs[:60]


# ══════════════════════════════════════════════
#  RISK SESSION MANAGEMENT
# ══════════════════════════════════════════════

def _ensure_risk_session(user_key: str, mode: str, enabled: bool) -> str:
    session_key       = f"tradesmart_risk_session_{user_key}_{mode}"
    prev_key          = f"tradesmart_prev_enabled_{user_key}_{mode}"
    force_stopped_key = _scope_key("tradesmart_force_stopped")
    force_reason_key  = _scope_key("tradesmart_force_stop_reason")
    force_key         = _scope_key("tradesmart_force_stop_key")

    was_enabled      = bool(st.session_state.get(prev_key, False))
    was_force_stopped = bool(st.session_state.get(force_stopped_key, False))

    if enabled and (not was_enabled or was_force_stopped):
        # Brand-new session
        st.session_state[session_key] = f"{user_key}:{mode}:{datetime.now().timestamp()}"
        st.session_state[f"tradesmart_session_start_{user_key}_{mode}"] = datetime.now().isoformat(timespec="seconds")
        _reset_session_accounting(user_key, mode, st.session_state[session_key])
        st.session_state[force_stopped_key] = False
        st.session_state.pop(force_reason_key, None)
        st.session_state.pop(force_key, None)
        _add_log("Risk Session Reset", "New session started. Previous P/L is the baseline.")

    if not enabled and was_enabled:
        _add_log("Agent OFF", "Live tracking stopped. Turn ON to start a fresh session.")

    st.session_state[prev_key] = bool(enabled)
    if not st.session_state.get(session_key):
        st.session_state[session_key] = f"{user_key}:{mode}:idle"
    return str(st.session_state[session_key])


# ══════════════════════════════════════════════
#  FORMATTING
# ══════════════════════════════════════════════

def _money(value: Any) -> str:
    try:
        val    = float(value or 0.0)
        prefix = "+" if val > 0 else ""
        return f"{prefix}${val:,.2f}"
    except Exception:
        return "—"


def _plain(value: Any) -> str:
    return escape(str(value if value not in (None, "") else "—"))


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except Exception:
        return float(default)


def _session_start_label(user_key: str, mode: str) -> str:
    raw = st.session_state.get(f"tradesmart_session_start_{user_key}_{mode}")
    if not raw:
        return "Not started"
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt.strftime("%I:%M:%S %p")
    except Exception:
        return str(raw)


def _reset_session_accounting(user_key: str, mode: str, session_id: str) -> None:
    st.session_state[_scope_key("tradesmart_session_accounting_id", user_key, mode)] = session_id
    # Baselines are captured from the first MT5 snapshot after the agent starts.
    # Balance delta is the most reliable page-level realized P/L because MT5 balance
    # changes only after a trade closes, while equity includes floating P/L.
    st.session_state[_scope_key("tradesmart_session_closed_baseline", user_key, mode)] = None
    st.session_state[_scope_key("tradesmart_session_balance_baseline", user_key, mode)] = None
    st.session_state[_scope_key("tradesmart_session_closed_pl", user_key, mode)] = 0.0
    st.session_state[_scope_key("tradesmart_session_combined_pl", user_key, mode)] = 0.0
    st.session_state[_scope_key("tradesmart_session_opened_tickets", user_key, mode)] = set()
    st.session_state[_scope_key("tradesmart_session_opened_count", user_key, mode)] = 0


def _apply_session_accounting(result: Dict[str, Any], risk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce TradeSmart page session accounting.
    A session starts when the agent is toggled ON and ends when it is toggled OFF.
    Closed P/L shown here is current MT5 closed P/L minus the baseline captured
    at the first snapshot of this TradeSmart session, so closed trades remain
    included after they close while the agent is running.
    """
    result = dict(result or {})
    account = dict(result.get("account") or {})
    user_key = str(risk.get("user_key") or _user_key())
    mode = str(risk.get("mode") or "Demo")
    session_id = str(risk.get("risk_session_id") or f"{user_key}:{mode}:idle")

    accounting_id_key = _scope_key("tradesmart_session_accounting_id", user_key, mode)
    baseline_key = _scope_key("tradesmart_session_closed_baseline", user_key, mode)
    balance_baseline_key = _scope_key("tradesmart_session_balance_baseline", user_key, mode)
    session_closed_key = _scope_key("tradesmart_session_closed_pl", user_key, mode)
    session_combined_key = _scope_key("tradesmart_session_combined_pl", user_key, mode)
    opened_tickets_key = _scope_key("tradesmart_session_opened_tickets", user_key, mode)
    opened_count_key = _scope_key("tradesmart_session_opened_count", user_key, mode)

    if st.session_state.get(accounting_id_key) != session_id:
        _reset_session_accounting(user_key, mode, session_id)

    closed_today_raw = account.get("closed_pl_today")
    closed_today = _float_value(closed_today_raw, _float_value(account.get("session_closed_pl"), 0.0))
    balance_now = _float_value(account.get("balance"), 0.0)

    if st.session_state.get(baseline_key) is None:
        # Baseline means: everything closed before the agent session started.
        st.session_state[baseline_key] = closed_today
    if st.session_state.get(balance_baseline_key) is None:
        # Balance baseline lets the page show realized P/L even if the agent does
        # not return refreshed closed_pl_today after a deal closes.
        st.session_state[balance_baseline_key] = balance_now

    closed_baseline = _float_value(st.session_state.get(baseline_key), 0.0)
    balance_baseline = _float_value(st.session_state.get(balance_baseline_key), balance_now)
    closed_today_delta = closed_today - closed_baseline
    balance_delta = balance_now - balance_baseline

    # Realized session P/L: prefer balance delta because it reflects closed trades
    # immediately after MT5 books the deal. Fall back to closed_pl_today delta when
    # balance is unavailable.
    session_closed = balance_delta if account.get("balance") not in (None, "") else closed_today_delta

    floating = _float_value(account.get("floating_pl"), 0.0)
    combined = session_closed + floating

    opened_tickets = st.session_state.get(opened_tickets_key)
    if not isinstance(opened_tickets, set):
        opened_tickets = set(opened_tickets or [])
    for collection_name in ("position_summary", "positions"):
        for pos in result.get(collection_name) or []:
            ticket = pos.get("ticket") or pos.get("position") or pos.get("order")
            if ticket not in (None, ""):
                opened_tickets.add(str(ticket))
    order_result = result.get("order_result") or {}
    if isinstance(order_result, dict):
        ticket = order_result.get("ticket") or order_result.get("order") or order_result.get("position")
        if ticket not in (None, ""):
            opened_tickets.add(str(ticket))
    opened_count = len(opened_tickets)

    account["session_closed_pl"] = session_closed
    account["combined_session_pl"] = combined
    account["session_baseline_closed_pl"] = closed_baseline
    account["session_balance_baseline"] = balance_baseline
    account["session_started_at"] = _session_start_label(user_key, mode)
    account["session_opened_trades"] = opened_count

    st.session_state[session_closed_key] = session_closed
    st.session_state[session_combined_key] = combined
    st.session_state[opened_tickets_key] = opened_tickets
    st.session_state[opened_count_key] = opened_count

    result["account"] = account
    result["session_opened_trades"] = opened_count
    result["session_id"] = session_id
    result["risk_session_id"] = session_id
    result["session_started_at"] = account.get("session_started_at")
    return result



def _emergency_flatten_positions(profile: Dict[str, Any], risk: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Best-effort close of open positions before toggling the agent off.
    Supports several method names so this page stays compatible with existing
    TradeSmartAgent versions without breaking if one method is missing.
    """
    close_risk = dict(risk or {})
    close_risk["force_close_reason"] = reason
    close_risk["emergency_stop"] = True
    close_risk["close_all"] = True
    agent = TradeSmartAgent(profile=profile, rules={**close_risk, "symbol": SYMBOL})
    for method_name in (
        "close_all_positions",
        "close_open_positions",
        "close_positions",
        "emergency_close_all",
        "flatten_positions",
    ):
        method = getattr(agent, method_name, None)
        if callable(method):
            try:
                result = method(reason=reason)
            except TypeError:
                result = method()
            if isinstance(result, dict):
                return _apply_session_accounting(result, risk)
            return {"ok": True, "event": "Emergency Close", "message": str(result)}

    # Last compatible fallback: run one more cycle with emergency flags.
    try:
        result = agent.run_cycle(execution_enabled=True)
        if isinstance(result, dict):
            return _apply_session_accounting(result, risk)
    except Exception as exc:
        return {"ok": False, "event": "Emergency Close Error", "message": str(exc)}
    return {"ok": False, "event": "Emergency Close", "message": "No close method was available on TradeSmartAgent."}

def _page_risk_breached(result: Dict[str, Any], risk: Dict[str, Any]) -> Tuple[bool, str]:
    max_loss = _float_value(risk.get("max_daily_loss_amount"), 0.0)
    if max_loss <= 0:
        return False, ""
    account = (result or {}).get("account") or {}
    session_closed = _float_value(account.get("session_closed_pl"), 0.0)
    floating = _float_value(account.get("floating_pl"), 0.0)
    combined = _float_value(account.get("combined_session_pl"), session_closed + floating)
    worst = min(session_closed, floating, combined)
    if worst <= -abs(max_loss):
        return True, (
            f"Max session risk reached: closed {_money(session_closed)}, "
            f"floating {_money(floating)}, total {_money(combined)}. Agent stopped."
        )
    return False, ""


# ══════════════════════════════════════════════
#  LIVE SUMMARY — only render when agent is ON
#  When agent is OFF this section is replaced by
#  the _build_off_session_html card (no duplicate).
# ══════════════════════════════════════════════

def _render_live_summary(result: Dict[str, Any], agent_on: bool) -> None:
    """
    Render the 6-metric live tracking grid.
    Only called when the agent is running.  The OFF snapshot card already
    shows these numbers, so we skip them when agent_on is False.
    """
    if not agent_on:
        return

    result  = result or {}
    account = result.get("account") or {}

    dot_class = "ts-live-summary-title"
    st.markdown(
        f'<div class="{dot_class}">Live Tracking Summary</div>',
        unsafe_allow_html=True,
    )

    def _m(label: str, raw: Any) -> str:
        return (
            f"<div class='ts-metric'>"
            f"<div class='ts-metric-label'>{escape(label)}</div>"
            f"<div class='ts-metric-value'>{escape(str(raw if raw not in (None, '') else '—'))}</div>"
            f"</div>"
        )

    # Pull the freshest values from the result
    balance    = account.get("balance")
    equity     = account.get("equity")
    float_pl   = account.get("floating_pl")
    sess_cl    = account.get("session_closed_pl")
    sess_total = account.get("combined_session_pl")
    open_cnt   = result.get("open_positions_count", account.get("open_positions", 0))
    started    = account.get("session_started_at") or result.get("session_started_at") or "Not started"
    session_opened = result.get("session_opened_trades", account.get("session_opened_trades", 0))

    html = "<div class='ts-summary'>" + "".join([
        _m("Balance",        _money(balance)),
        _m("Equity",         _money(equity)),
        _m("Floating P/L",   _money(float_pl)),
        _m("Session Closed", _money(sess_cl)),
        _m("Session P/L",    _money(sess_total)),
        _m("Open Trades",    open_cnt),
        _m("Session Start",  started),
        _m("Session Trades", session_opened),
    ]) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════
#  LOGS PANEL
# ══════════════════════════════════════════════

def _render_logs() -> None:
    logs = st.session_state.get(_scope_key("tradesmart_logs"), [])
    if not logs:
        st.markdown(
            "<div class='ts-log-wrap'>"
            "<div class='ts-log-item'>"
            "<div class='ts-log-title'>No logs yet</div>"
            "<div class='ts-log-msg'>Connect MT5 and turn the agent ON to start live tracking.</div>"
            "</div></div>",
            unsafe_allow_html=True,
        )
        return
    html = ["<div class='ts-log-wrap'>"]
    for item in logs[:35]:
        html.append(
            f"<div class='ts-log-item'>"
            f"<div class='ts-log-title'>{escape(item.get('time',''))} • {escape(item.get('title','Update'))}</div>"
            f"<div class='ts-log-msg'>{escape(item.get('message',''))}</div>"
            f"</div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


# ══════════════════════════════════════════════
#  AGENT OFF SNAPSHOT CARD (self-contained HTML)
#  Shows last known account numbers without leaking username.
# ══════════════════════════════════════════════

def _stopped_result(mode: str, reason: str, risk: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "ok": True, "phase": "stopped", "event": "Agent OFF",
        "message": reason,
        "thinking": "Agent is OFF. Turn ON to start a new TradeSmart session.",
        "mode": mode, "symbol": SYMBOL, "agent_off": True,
        "decision": {"action": "OFF", "reason": reason},
        "risk": risk or {},
    }


def _run_final_session_snapshot(
    profile: Dict[str, Any], risk: Dict[str, Any], reason: str
) -> Dict[str, Any]:
    """One-shot snapshot to capture final MT5 account numbers when agent turns OFF."""
    snap_risk = dict(risk or {})
    snap_risk["max_daily_loss_amount"] = 0.0
    snap_risk["market_open"]           = False
    result = TradeSmartAgent(profile=profile, rules={**snap_risk, "symbol": SYMBOL}).connect_only()
    result = _apply_session_accounting(result, risk)
    result["agent_off"] = True
    result["phase"]     = "stopped"
    result["event"]     = "Session Paused"
    result["message"]   = reason
    result["thinking"]  = "Execution paused. Session totals captured from MT5."
    result["decision"]  = {"action": "OFF", "reason": reason}
    result["risk"]      = snap_risk
    return result


def _build_off_session_html(
    result: Dict[str, Any], profile: Dict[str, Any], mode: str
) -> str:
    """
    Compact OFF-state card — shows account numbers, masked login, mode, time.
    Does NOT show any user name / display name string.
    """
    result      = result or {}
    account     = result.get("account") or {}
    open_trades = result.get("open_positions_count", account.get("open_positions", 0))
    message     = result.get("message") or "Agent is OFF. Turn ON to start a new TradeSmart session."
    updated     = datetime.now().strftime("%I:%M:%S %p")
    login_mask  = _masked_login(profile)
    started     = account.get("session_started_at") or result.get("session_started_at") or "Not started"
    session_opened = result.get("session_opened_trades", account.get("session_opened_trades", 0))

    return f"""<!doctype html><html><head><style>
html,body{{margin:0;padding:0;background:transparent;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:rgba(255,255,255,.94);overflow:hidden}}
.ts-off-card{{box-sizing:border-box;width:100%;min-height:240px;padding:18px;border-radius:24px;
  background:radial-gradient(circle at 0% 0%,rgba(0,255,163,.14),transparent 38%),
             radial-gradient(circle at 100% 0%,rgba(80,145,255,.15),transparent 34%),
             linear-gradient(145deg,rgba(6,18,34,.96),rgba(8,32,52,.86));
  border:1px solid rgba(0,255,163,.20);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 22px 60px rgba(0,0,0,.32)}}
.ts-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:14px}}
.ts-head-left{{min-width:0}}
.ts-title{{font-size:14px;font-weight:950;letter-spacing:-.01em;color:#fff}}
.ts-sub{{font-size:11px;line-height:1.4;color:rgba(255,255,255,.60);margin-top:3px}}
.ts-badge{{flex:0 0 auto;border-radius:999px;padding:5px 11px;font-size:10px;font-weight:900;letter-spacing:.06em;
  color:rgba(255,170,180,.96);border:1px solid rgba(255,96,112,.36);background:rgba(255,96,112,.10)}}
.ts-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}}
.ts-box{{min-width:0;border-radius:16px;padding:12px 13px;
  background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.035));
  border:1px solid rgba(255,255,255,.10)}}
.ts-label{{font-size:9.5px;font-weight:900;letter-spacing:.09em;text-transform:uppercase;
  color:rgba(255,255,255,.52);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ts-value{{margin-top:6px;font-size:15px;font-weight:950;letter-spacing:-.02em;
  color:rgba(255,255,255,.94);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ts-note{{margin-top:12px;font-size:11.5px;line-height:1.4;color:rgba(255,255,255,.68)}}
@media(max-width:560px){{.ts-grid{{grid-template-columns:1fr 1fr}}.ts-value{{font-size:13px}}}}
</style></head><body>
<div class='ts-off-card'>
  <div class='ts-head'>
    <div class='ts-head-left'>
      <div class='ts-title'>Session Results</div>
      <div class='ts-sub'>{_plain(mode)} account {_plain(login_mask)} · XAUUSD · start {_plain(started)} · updated {_plain(updated)}</div>
    </div>
    <div class='ts-badge'>AGENT OFF</div>
  </div>
  <div class='ts-grid'>
    <div class='ts-box'><div class='ts-label'>Balance</div><div class='ts-value'>{_money(account.get('balance'))}</div></div>
    <div class='ts-box'><div class='ts-label'>Equity</div><div class='ts-value'>{_money(account.get('equity'))}</div></div>
    <div class='ts-box'><div class='ts-label'>Floating P/L</div><div class='ts-value'>{_money(account.get('floating_pl'))}</div></div>
    <div class='ts-box'><div class='ts-label'>Session Closed</div><div class='ts-value'>{_money(account.get('session_closed_pl'))}</div></div>
    <div class='ts-box'><div class='ts-label'>Session P/L</div><div class='ts-value'>{_money(account.get('combined_session_pl'))}</div></div>
    <div class='ts-box'><div class='ts-label'>Open Trades</div><div class='ts-value'>{_plain(open_trades)}</div></div>
    <div class='ts-box'><div class='ts-label'>Session Trades</div><div class='ts-value'>{_plain(session_opened)}</div></div>
  </div>
  <div class='ts-note'>{_plain(message)}</div>
</div>
</body></html>"""


# ══════════════════════════════════════════════
#  AGENT CYCLE RUNNER
# ══════════════════════════════════════════════

def _run_live_cycle(
    profile: Dict[str, Any], risk: Dict[str, Any], enabled: bool
) -> Dict[str, Any]:
    agent  = TradeSmartAgent(profile=profile, rules={**risk, "symbol": SYMBOL})
    result = agent.run_cycle(execution_enabled=enabled)
    result = _apply_session_accounting(result, risk)
    try:
        draw_count = write_draw_commands(
            result,
            project_root=_project_root(),
            user_key=str(risk.get("user_id") or risk.get("user_key") or "default"),
        )
        result["draw_command_count"] = draw_count
    except Exception as exc:
        result["draw_error"] = str(exc)
    return result


# ══════════════════════════════════════════════
#  LIVE FRAGMENT
#  • Agent ON  → run cycle + show live thinking card + live summary grid
#  • Agent OFF → show static OFF snapshot card ONLY (no live summary grid)
#  The fragment ONLY runs under st.fragment when the agent is ON.
# ══════════════════════════════════════════════

def _live_fragment(
    profile: Dict[str, Any],
    risk: Dict[str, Any],
    agent_key: str,
    market_open: bool,
    market_reason: str,
) -> Dict[str, Any]:
    force_key = st.session_state.get(_scope_key("tradesmart_force_stop_key"))
    if force_key == agent_key:
        enabled = False
    else:
        enabled = bool(st.session_state.get(agent_key, False))

    # Retrieve last known result (never stale — always the freshest snapshot)
    result = (
        st.session_state.get(_scope_key("tradesmart_last_result"))
        or _stopped_result(risk.get("mode", "Demo"), "Agent is OFF.", risk)
    )
    result = _apply_session_accounting(result, risk)

    # ── Market closed mid-session ─────────────────────────────────
    if enabled and not market_open:
        st.session_state[agent_key] = False
        st.session_state[f"tradesmart_prev_enabled_{risk.get('user_key')}_{risk.get('mode')}"] = False
        st.session_state[_scope_key("tradesmart_force_stop_key")] = agent_key
        st.session_state[_scope_key("tradesmart_force_stopped")]  = True
        st.session_state[_scope_key("tradesmart_force_stop_reason")] = market_reason
        result = (
            _run_final_session_snapshot(profile, risk, market_reason)
            if bool(risk.get("connected"))
            else _stopped_result(risk.get("mode", "Demo"), market_reason, risk)
        )
        st.session_state[_scope_key("tradesmart_last_result")] = result
        _add_log("Market Closed", market_reason, result)
        enabled = False

    # ── Agent ON — run live cycle ─────────────────────────────────
    elif enabled:
        result = _run_live_cycle(profile, risk, enabled=True)
        st.session_state[_scope_key("tradesmart_last_result")] = result
        _add_log(
            result.get("event", "Agent Scan"),
            result.get("message") or result.get("thinking") or "Scan complete.",
            result,
        )
        # Max session loss kill switch: checks closed, floating, and combined P/L every cycle.
        page_risk_hit, page_risk_msg = _page_risk_breached(result, risk)
        if result.get("max_daily_loss_reached") or page_risk_hit:
            stop_msg = page_risk_msg or result.get("message", "Max session risk reached.")
            close_result = _emergency_flatten_positions(profile, risk, stop_msg)
            _add_log(
                close_result.get("event", "Emergency Close"),
                close_result.get("message", "Risk lock attempted to close open positions."),
                close_result,
            )
            final    = _run_final_session_snapshot(profile, risk, stop_msg)
            st.session_state[agent_key] = False
            st.session_state[f"tradesmart_prev_enabled_{risk.get('user_key')}_{risk.get('mode')}"] = False
            st.session_state[_scope_key("tradesmart_force_stop_key")]   = agent_key
            st.session_state[_scope_key("tradesmart_force_stopped")]    = True
            st.session_state[_scope_key("tradesmart_force_stop_reason")] = stop_msg
            result  = final
            enabled = False
            st.session_state[_scope_key("tradesmart_last_result")] = result

    # ── Agent OFF — preserve last snapshot, mark it off ──────────
    else:
        result["agent_off"] = True
        result["phase"]     = "stopped"
        result["decision"]  = {
            **(result.get("decision") or {}),
            "action": "OFF",
            "reason": result.get("message") or "Agent is OFF.",
        }
        st.session_state[_scope_key("tradesmart_last_result")] = result

    # ── Render ────────────────────────────────────────────────────
    is_off = bool(result.get("agent_off")) or str(
        (result.get("decision") or {}).get("action", "")
    ).upper() == "OFF"

    if is_off:
        # Static OFF card — only refreshes once when agent turns off (manual snapshot)
        components.html(
            _build_off_session_html(result, profile, str(risk.get("mode", "Demo"))),
            height=285,
            scrolling=False,
        )
        # ← No live summary grid when OFF
    else:
        # Live thinking card (auto-refreshed by the fragment)
        components.html(build_live_thinking_html(result), height=390, scrolling=False)
        # Live tracking summary grid — only shown when agent is truly ON
        _render_live_summary(result, agent_on=True)

    return result


# ══════════════════════════════════════════════
#  MAIN PAGE RENDERER
# ══════════════════════════════════════════════

def render_tradesmart_page(role: str | None = None) -> None:
    _inject_css()
    user_key = _user_key()
    market_open, market_reason, et_now = _market_status()

    # ── HERO ──────────────────────────────────────────────────────
    st.markdown(
        "<div class='ts-hero'>"
        "<div class='ts-title'>⚡ TradeSmart Agent</div>"
        "<div class='ts-muted'>"
        "Smart money scalping engine — multi-timeframe SMC liquidity analysis, "
        "order block detection, FVG targeting, and 1:2 minimum R:R execution. "
        "Live chart drawings pushed to MT5 every cycle."
        "</div></div>",
        unsafe_allow_html=True,
    )

    # ── ACCOUNT MODE ──────────────────────────────────────────────
    connected_key      = f"tradesmart_connected_{user_key}"
    connected_mode_key = f"tradesmart_connected_mode_{user_key}"
    connected          = bool(st.session_state.get(connected_key, False))
    selected_mode_key  = f"tradesmart_mode_{user_key}"

    if connected:
        # Lock mode selector while connected
        st.session_state[selected_mode_key] = st.session_state.get(
            connected_mode_key,
            st.session_state.get(selected_mode_key, "Demo"),
        )

    mode    = st.radio("Account Mode", ["Demo", "Live"], horizontal=True, key=selected_mode_key, disabled=connected)
    profile = _load_mt5_profile(mode)
    _set_scope(user_key, mode)
    complete = _complete_profile(profile)

    # Connection + market status pill
    conn_text = "CONNECTED" if connected else "DISCONNECTED"
    pill_cls  = "ts-pill ts-pill--live" if connected else "ts-pill ts-pill--off"
    st.markdown(
        f"<div class='{pill_cls}'>"
        f"<span class='ts-dot{'' if connected else ' off'}'></span>"
        f"{escape(conn_text)} &bull; {escape(mode)} profile: {escape(_masked_login(profile))} "
        f"&bull; Market ET {escape(et_now.strftime('%I:%M %p'))}"
        f"</div>",
        unsafe_allow_html=True,
    )
    if connected:
        st.info("Disconnect MT5 before switching Demo/Live.")
    if not market_open:
        st.warning(market_reason)
    if not complete:
        st.warning(f"Save your {mode} MT5 login/password/server in Settings before connecting.")

    # ── RISK SETTINGS ─────────────────────────────────────────────
    _section("Risk Settings")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        trade_volume = st.number_input(
            "Trade volume", min_value=0.01, max_value=100.0,
            value=float(st.session_state.get("ts_trade_volume", 0.01)),
            step=0.01, key="ts_trade_volume",
        )
    with c2:
        max_open = st.number_input(
            "Max open trades", min_value=1, max_value=20,
            value=int(st.session_state.get("ts_max_open", 1)),
            step=1, key="ts_max_open",
        )
    with c3:
        max_loss = st.number_input(
            "Max daily loss $", min_value=0.0, max_value=100000.0,
            value=float(st.session_state.get("ts_max_loss", 10.0)),
            step=1.0, key="ts_max_loss",
        )
    with c4:
        min_score = st.slider(
            "Min strategy score", min_value=0.40, max_value=0.95,
            value=float(st.session_state.get("ts_min_score", 0.62)),
            step=0.01, key="ts_min_score",
        )

    risk = {
        "mode":                   mode,
        "trade_volume":           trade_volume,
        "volume":                 trade_volume,          # alias agents expect
        "max_open_trades":        int(max_open),
        "max_daily_loss_amount":  float(max_loss),
        "min_strategy_score":     float(min_score),
        "market_open":            bool(market_open),
        "market_reason":          market_reason,
        "user_key":               user_key,
        "user_id":                _safe_user_id(user_key),
        "output_scope":           f"{_safe_user_id(user_key)}_{mode.lower()}",
        "connected":              bool(connected),
    }

    # ── CONNECTION + AGENT CONTROL ────────────────────────────────
    _section("Connection + Live Agent Control")
    agent_key = f"tradesmart_agent_enabled_{user_key}_{mode}"

    # Clear any stale force-stop flag that matches this agent key
    if st.session_state.get(_scope_key("tradesmart_force_stop_key")) == agent_key:
        st.session_state[agent_key] = False
        st.session_state[f"tradesmart_prev_enabled_{user_key}_{mode}"] = False
        st.session_state.pop(_scope_key("tradesmart_force_stop_key"), None)

    cols = st.columns([1.2, 1.2, 2.2])
    with cols[0]:
        connect_label = "Disconnect MT5" if connected else "Connect MT5"
        if st.button(connect_label, use_container_width=True, disabled=(not complete and not connected)):
            if connected:
                result = TradeSmartAgent(profile=profile, rules=risk).disconnect_only()
                st.session_state[connected_key]  = False
                st.session_state.pop(connected_mode_key, None)
                st.session_state[agent_key]      = False
                result["agent_off"]              = True
                st.session_state[_scope_key("tradesmart_last_result")] = result
                _add_log("Disconnected", result.get("message", "MT5 disconnected."), result)
            else:
                result = TradeSmartAgent(profile=profile, rules=risk).connect_only()
                st.session_state[_scope_key("tradesmart_last_result")] = result
                st.session_state[connected_key]  = bool(result.get("ok"))
                if result.get("ok"):
                    st.session_state[connected_mode_key] = mode
                _add_log(
                    result.get("event", "Connect"),
                    result.get("message", "MT5 connect complete."),
                    result,
                )
                st.rerun()

    with cols[1]:
        current_enabled = bool(st.session_state.get(agent_key, False))
        toggle_label    = "TradeSmart Agent: ON" if current_enabled else "TradeSmart Agent: OFF"
        enabled = st.toggle(
            toggle_label,
            value=current_enabled,
            key=agent_key,
            disabled=(not complete or not connected or not market_open),
        )
        if not market_open and current_enabled:
            st.session_state[agent_key] = False
            enabled = False

    with cols[2]:
        if st.session_state.get(_scope_key("tradesmart_force_stopped")):
            st.error(
                st.session_state.get(
                    _scope_key("tradesmart_force_stop_reason"),
                    "Agent stopped by risk lock.",
                )
            )
            if st.button("Clear stop message after review"):
                st.session_state[_scope_key("tradesmart_force_stopped")]    = False
                st.session_state.pop(_scope_key("tradesmart_force_stop_reason"), None)
                st.session_state.pop(_scope_key("tradesmart_force_stop_key"),   None)
                st.rerun()

    # ── RISK SESSION + MANUAL OFF SNAPSHOT ───────────────────────
    prev_before_toggle = bool(
        st.session_state.get(f"tradesmart_prev_enabled_{user_key}_{mode}", False)
    )
    risk["risk_session_id"] = _ensure_risk_session(user_key, mode, enabled)

    # User just toggled OFF → capture a one-time snapshot so numbers are fresh
    manual_off_event = bool(connected and prev_before_toggle and not enabled)
    if manual_off_event:
        final_result = _run_final_session_snapshot(
            profile, risk,
            "Agent is OFF. Session totals captured at stop.",
        )
        st.session_state[_scope_key("tradesmart_last_result")] = final_result
        _add_log(
            "Session Snapshot",
            "Final session totals captured after agent turned OFF.",
            final_result,
        )

    # ── STATUS PILL (above thinking section) ─────────────────────
    if enabled:
        st.markdown(
            "<div class='ts-pill ts-pill--live'>"
            "<span class='ts-spinner'></span>"
            "Agent ON — scanning, tracking, and executing every 3 seconds."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='ts-pill ts-pill--off'>"
            "<span class='ts-dot off'></span>"
            "Agent OFF — execution is stopped. Session Results stay locked until the next start."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── THINKING + LIVE TRACKING ─────────────────────────────────
    _section("TradeSmart Thinking")

    if enabled and hasattr(st, "fragment"):
        # Fragment ONLY created when agent is ON — stops auto-refresh when OFF
        @st.fragment(run_every=f"{REFRESH_ON_SECONDS}s")
        def _frag() -> None:
            _live_fragment(profile, risk, agent_key, market_open, market_reason)

        _frag()
    else:
        # Agent OFF: single render, no fragment, no auto-refresh
        _live_fragment(profile, risk, agent_key, market_open, market_reason)

    # ── AGENT LOG ────────────────────────────────────────────────
    _section("Agent Log")
    _render_logs()


# ══════════════════════════════════════════════
#  ENTRY POINT ALIASES
# ══════════════════════════════════════════════

def render_page(role: str | None = None) -> None:
    render_tradesmart_page(role)


def render_tradesmart(role: str | None = None) -> None:
    render_tradesmart_page(role)


def render_frontend_tradesmart_page(role: str | None = None) -> None:
    render_tradesmart_page(role)


def render_frontend_tools_page(role: str | None = None) -> None:
    render_tradesmart_page(role)
