from __future__ import annotations

from html import escape
import streamlit as st


def _html(markup: str) -> None:
    """Render real HTML without Streamlit/Markdown escaping it as visible text."""
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _trend_class(value: float) -> str:
    if value > 0:
        return "du-trend-up"
    if value < 0:
        return "du-trend-down"
    return "du-trend-flat"


def _trend_icon(value: float) -> str:
    if value > 0:
        return "▲"
    if value < 0:
        return "▼"
    return "●"


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _kpi_card_html(card: dict) -> str:
    label = escape(str(card.get("label", "")))
    icon = escape(str(card.get("icon", "")))
    value = escape(str(card.get("value", "")))
    unit = escape(str(card.get("unit", "")))
    sub = escape(str(card.get("sub", "")))

    trend = card.get("trend")
    trend_html = ""
    value_cls = ""
    if trend is not None:
        trend_value = _num(trend)
        trend_cls = _trend_class(trend_value)
        value_cls = trend_cls if trend_value != 0 else ""
        trend_html = f'<span class="du-kpi-trend {trend_cls}">{_trend_icon(trend_value)}</span>'

    progress_html = ""
    if "progress" in card:
        pct = max(0.0, min(100.0, _num(card.get("progress"))))
        progress_cls = "good" if pct >= 50 else "warn"
        progress_html = (
            '<div class="du-kpi-progress-track" aria-label="Win rate progress">'
            f'<div class="du-kpi-progress-fill {progress_cls}" style="width:{pct:.1f}%"></div>'
            '</div>'
        )

    unit_html = f'<span class="du-kpi-unit">{unit}</span>' if unit else ""

    return f"""
    <section class="du-kpi-card" aria-label="{label}">
        <div class="du-kpi-top">
            <span class="du-kpi-icon">{icon}</span>
            <span class="du-kpi-label">{label}</span>
            {trend_html}
        </div>
        <div class="du-kpi-value {value_cls}">
            <span class="du-kpi-number">{value}</span>{unit_html}
        </div>
        {progress_html}
        <div class="du-kpi-sub">{sub}</div>
    </section>
    """


def render_kpi_cards(data):
    account = data.get("account", {}) or {}
    metrics = data.get("metrics", {}) or {}
    currency = str(account.get("currency") or "USD")

    balance = _num(account.get("balance"))
    equity = _num(account.get("equity"))
    daily_pnl = _num(metrics.get("daily_pnl"))
    win_rate = _num(metrics.get("win_rate"))
    closed = int(_num(metrics.get("closed_trades")))
    eq_delta = equity - balance

    cards = [
        {
            "icon": "💰",
            "label": "Balance",
            "value": _money(balance),
            "unit": currency,
            "sub": "Account balance",
            "trend": None,
        },
        {
            "icon": "📊",
            "label": "Equity",
            "value": _money(equity),
            "unit": currency,
            "sub": f"{'+' if eq_delta >= 0 else ''}{_money(eq_delta)} {currency} floating",
            "trend": eq_delta,
        },
        {
            "icon": "📈" if daily_pnl >= 0 else "📉",
            "label": "Daily P/L",
            "value": _money(daily_pnl),
            "unit": currency,
            "sub": "Since midnight",
            "trend": daily_pnl,
        },
        {
            "icon": "🎯",
            "label": "Win Rate",
            "value": f"{win_rate:.1f}%",
            "unit": "",
            "sub": f"{closed:,} closed trades",
            "trend": None,
            "progress": win_rate,
        },
    ]

    cols = st.columns(4, gap="medium")
    for col, card in zip(cols, cards):
        with col:
            _html(_kpi_card_html(card))
