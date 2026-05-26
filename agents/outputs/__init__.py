from __future__ import annotations

from html import escape
from typing import Any, Dict, List


def _safe(value: Any) -> str:
    return escape(str(value if value is not None else "—"))


def _num(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return _safe(value)


def _position_line(result: Dict[str, Any]) -> str:
    summary = result.get("position_summary") or []
    positions = result.get("positions") or []

    if summary:
        parts = []
        for pos in summary[:5]:
            parts.append(
                f"{_safe(pos.get('direction'))} ticket {_safe(pos.get('ticket'))} • "
                f"volume {_safe(pos.get('volume'))} • P/L {_num(pos.get('profit'))} • "
                f"candles {_safe(pos.get('candles_since_open'))}"
            )
        return " | ".join(parts)

    if not positions:
        return "No open TradeSmart position is currently being tracked."

    chunks = []
    for pos in positions[:5]:
        ticket = _safe(pos.get("ticket"))
        profit = _num(pos.get("profit"))
        volume = _safe(pos.get("volume"))
        pos_type = int(pos.get("type", 0) or 0)
        direction = "BUY" if pos_type == 0 else "SELL"
        chunks.append(f"{direction} ticket {ticket} • volume {volume} • P/L {profit}")
    return " | ".join(chunks)


def build_live_thinking_html(result: Dict[str, Any]) -> str:
    """
    Neutral TradeSmart output hook.

    The page renders this inside an isolated component iframe, so the output
    cannot leak CSS or show raw markup on the main app.
    """
    result = result or {}
    decision = result.get("decision") or {}
    candle = result.get("last_closed_m1") or {}
    strategy = result.get("strategy") or "strategy core"
    thinking = result.get("thinking") or result.get("message") or "TradeSmart checked the market."
    event = result.get("event") or "Agent Update"
    action = str(decision.get("action") or "NONE").upper()
    account = result.get("account") or {}
    open_count = result.get("open_positions_count", len(result.get("positions") or []))
    mode = result.get("mode", "—")
    symbol = result.get("symbol", "XAUUSD")
    order = result.get("order_result") or {}

    candle_line = (
        f"O {_safe(candle.get('open'))} • H {_safe(candle.get('high'))} • "
        f"L {_safe(candle.get('low'))} • C {_safe(candle.get('close'))}"
    )

    order_line = ""
    if result.get("order_sent"):
        order_line = f"<div class='meta good'>Execution: order accepted by MT5. {_safe(order.get('message', ''))}</div>"
    elif isinstance(order, dict) and order.get("message"):
        order_line = f"<div class='meta warn'>Execution: {_safe(order.get('message'))}</div>"

    return f"""<!doctype html>
<html>
<head>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: rgba(255,255,255,.94);
      overflow: hidden;
    }}
    .box {{
      padding: 14px 16px;
      border-radius: 18px;
      background: linear-gradient(145deg, rgba(0,255,163,.085), rgba(255,255,255,.045));
      border: 1px solid rgba(0,255,163,.20);
      box-sizing: border-box;
      min-height: 145px;
    }}
    .head {{
      font-weight: 900;
      display: flex;
      align-items: center;
      margin-bottom: 7px;
      color: rgba(255,255,255,.96);
    }}
    .spin {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      border: 2px solid rgba(255,255,255,.18);
      border-top-color: #00ffa3;
      animation: spin .9s linear infinite;
      display:inline-block;
      margin-right: 8px;
      flex: 0 0 auto;
    }}
    .msg {{
      font-size: 13px;
      line-height: 1.42;
      color: rgba(255,255,255,.86);
      margin-top: 4px;
      white-space: normal;
      word-break: break-word;
    }}
    .meta {{
      font-size: 12px;
      line-height: 1.35;
      color: rgba(255,255,255,.66);
      margin-top: 4px;
      white-space: normal;
      word-break: break-word;
    }}
    .good {{ color: rgba(0,255,163,.82); }}
    .warn {{ color: rgba(255,210,120,.86); }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="box">
    <div class="head"><span class="spin"></span>TradeSmart Thinking</div>
    <div class="msg"><strong>{_safe(event)}</strong> — {_safe(thinking)}</div>
    <div class="meta">Mode: {_safe(mode)} • Symbol: {_safe(symbol)} • Strategy: {_safe(strategy)} • Direction: {_safe(action)} • Open trades: {_safe(open_count)}</div>
    <div class="meta">Account: balance {_num(account.get('balance'))} • equity {_num(account.get('equity'))} • currency {_safe(account.get('currency'))}</div>
    <div class="meta">Tracking: {_position_line(result)}</div>
    <div class="meta">Last closed M1: {candle_line}</div>
    {order_line}
  </div>
</body>
</html>"""
