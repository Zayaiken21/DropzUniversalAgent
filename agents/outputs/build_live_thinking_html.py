from __future__ import annotations

from html import escape
from typing import Any, Dict


def _safe(v: Any) -> str:
    return escape(str(v if v not in (None, "") else "—"))


def _num(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return _safe(v)


def _badge(text: str, cls: str = "") -> str:
    return f"<span class='badge {cls}'>{_safe(text)}</span>"


def _positions(result: Dict[str, Any]) -> str:
    items = result.get("position_summary") or result.get("positions") or []
    if not items:
        return "No open TradeSmart position is currently being tracked."
    out = []
    for p in items[:5]:
        side = p.get("direction")
        if not side:
            side = "BUY" if int(p.get("type", 0) or 0) == 0 else "SELL"
        out.append(f"{_safe(side)} #{_safe(p.get('ticket'))} • vol {_safe(p.get('volume'))} • P/L {_num(p.get('profit'))}")
    return " | ".join(out)


def build_live_thinking_html(result: Dict[str, Any]) -> str:
    result = result or {}
    decision = result.get("decision") or {}
    strategy_info = result.get("strategy_info") or {}
    raw = strategy_info.get("raw") if isinstance(strategy_info.get("raw"), dict) else {}
    data = decision.get("data") or raw.get("data") or {}
    rng = data.get("range") or {}
    profile = data.get("volume_profile") or {}
    d1 = data.get("d1_context") or {}
    h4 = data.get("h4_context") or {}
    h1 = data.get("h1_context") or {}
    session = data.get("session") or {}
    account = result.get("account") or {}
    candle = result.get("last_closed_m1") or {}
    agent_off = bool(result.get("agent_off")) or str(result.get("phase", "")).lower() in {"stopped", "disconnect", "market_closed"} or str(decision.get("action", "")).upper() == "OFF"
    raw_action = str(decision.get("action") or result.get("action") or "SCAN").upper()
    action = "OFF" if agent_off else raw_action
    score = "—" if agent_off else decision.get("score", decision.get("confidence", "—"))
    event = result.get("event") or ("Agent OFF" if agent_off else "TradeSmart Agent Scan")
    thinking = result.get("thinking") or result.get("message") or decision.get("reason") or "Scanning."
    mode = result.get("mode", "—")
    open_count = result.get("open_positions_count", len(result.get("positions") or []))
    session_started_at = result.get("session_started_at") or account.get("session_started_at") or "Not started"
    closed_updates = result.get("session_closed_trade_events", 0)
    location = data.get("location") or "—"
    market = result.get("market_reason") or "Market status OK."

    if agent_off:
        badges = "".join([
            _badge("AGENT OFF", "off"),
            _badge(str(result.get("phase") or "STOPPED")),
            _badge(str(result.get("market_time_et") or "ET time —")),
        ])
    else:
        badges = "".join([
            _badge(action, "buy" if action == "BUY" else "sell" if action == "SELL" else ""),
            _badge(f"score {score}"),
            _badge(str(session.get("name") or "SESSION")),
            _badge(str(location)),
            _badge("LOCKED" if rng.get("locked") else "BUILDING"),
        ])

    candle_line = f"O {_num(candle.get('open'))} • H {_num(candle.get('high'))} • L {_num(candle.get('low'))} • C {_num(candle.get('close'))}"
    order = result.get("order_result") or {}
    order_line = ""
    if result.get("order_sent") and not agent_off:
        order_line = f"<div class='row good'><b>Execution</b><span>Order accepted. {_safe(order.get('message') if isinstance(order, dict) else order)}</span></div>"
    elif isinstance(order, dict) and order.get("message") and not agent_off:
        order_line = f"<div class='row warn'><b>Execution</b><span>{_safe(order.get('message'))}</span></div>"

    status_title = "Session Results" if agent_off else "TradeSmart Agent Thinking"
    off_rows = ""
    if agent_off:
        off_rows = f"""
<div class='row'><b>Status</b><span>Agent OFF • waiting for manual start</span></div>
<div class='row'><b>Next Step</b><span>Review results, then toggle ON for a new risk session</span></div>
<div class='row'><b>Market</b><span>{_safe(market)}</span></div>
"""

    return f"""<!doctype html><html><head><style>
html,body{{margin:0;padding:0;background:transparent;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:rgba(255,255,255,.94);overflow:hidden}}
.box{{padding:15px 16px;border-radius:20px;background:radial-gradient(circle at 0% 0%,rgba(0,255,163,.15),transparent 34%),linear-gradient(145deg,rgba(0,255,163,.09),rgba(80,145,255,.045));border:1px solid rgba(0,255,163,.24);box-sizing:border-box;min-height:342px}}
.head{{font-weight:950;display:flex;align-items:center;margin-bottom:8px;color:#fff}}
.spin{{width:16px;height:16px;border-radius:50%;border:2px solid rgba(255,255,255,.20);border-top-color:#00ffa3;animation:spin .9s linear infinite;display:inline-block;margin-right:8px}}
.badges{{display:flex;gap:6px;flex-wrap:wrap;margin:5px 0 9px}}
.badge{{font-size:10.5px;font-weight:850;padding:4px 7px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.13);color:rgba(255,255,255,.84)}}
.badge.buy{{border-color:rgba(0,255,163,.45);color:rgba(0,255,163,.95)}}.badge.sell{{border-color:rgba(255,90,110,.48);color:rgba(255,120,135,.95)}}.badge.off{{border-color:rgba(255,96,112,.50);color:rgba(255,140,150,.96)}}
.msg{{font-size:13px;line-height:1.38;color:rgba(255,255,255,.88);margin-bottom:7px;word-break:break-word}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;margin-top:7px}}
.row{{font-size:12px;line-height:1.34;display:flex;gap:8px;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.06);padding:4px 0;color:rgba(255,255,255,.78)}}
.row b{{color:rgba(255,255,255,.96);font-size:11px;text-transform:uppercase;letter-spacing:.05em}}.row span{{text-align:right}}.good{{color:rgba(0,255,163,.88)}}.warn{{color:rgba(255,210,120,.88)}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
</style></head><body><div class='box'>
<div class='head'><span class='spin'></span>{_safe(status_title)}</div>
<div class='badges'>{badges}</div>
<div class='msg'><strong>{_safe(event)}</strong> — {_safe(thinking)}</div>
<div class='grid'>
{off_rows}
<div class='row'><b>Mode</b><span>{_safe(mode)} • XAUUSD • open {open_count}</span></div>
<div class='row'><b>Session Start</b><span>{_safe(session_started_at)} • closed updates {closed_updates}</span></div>
<div class='row'><b>Account</b><span>{_num(account.get('balance'))} bal • {_num(account.get('equity'))} eq</span></div>
<div class='row'><b>Session P/L</b><span>{_num(account.get('combined_session_pl'))} total • {_num(account.get('floating_pl'))} floating</span></div>
<div class='row'><b>Closed P/L</b><span>{_num(account.get('session_closed_pl'))} session • {_num(account.get('closed_pl_today'))} today</span></div>
<div class='row'><b>D1</b><span>{_safe(d1.get('bias'))} • H {_num(d1.get('high'))} L {_num(d1.get('low'))}</span></div>
<div class='row'><b>H4</b><span>{_safe(h4.get('bias'))} • H {_num(h4.get('high'))} L {_num(h4.get('low'))}</span></div>
<div class='row'><b>H1</b><span>{_safe(h1.get('bias'))} • H {_num(h1.get('high'))} L {_num(h1.get('low'))}</span></div>
<div class='row'><b>First15</b><span>L {_num(rng.get('range_low'))} • M {_num(rng.get('range_mid'))} • H {_num(rng.get('range_high'))}</span></div>
<div class='row'><b>Volume</b><span>M1 {_num(data.get('volume_ratio_m1'))} • M5 {_num(data.get('volume_ratio_m5'))}</span></div>
<div class='row'><b>Profile</b><span>VAL {_num(profile.get('val'))} • POC {_num(profile.get('poc'))} • VAH {_num(profile.get('vah'))}</span></div>
<div class='row'><b>Tracking</b><span>{_positions(result)}</span></div>
<div class='row'><b>Last M1</b><span>{candle_line}</span></div>
{order_line}
</div></div></body></html>"""
