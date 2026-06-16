from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        # Start the next TradeSmart session clean so old Session Results do not
        # bleed into the new run before the first fresh MT5 snapshot arrives.
        st.session_state.pop(_scope_key("tradesmart_last_result", user_key, mode), None)
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


def _stable_container(height: int):
    """Return a fixed-height Streamlit container when supported.
    This keeps the TradeSmart live area from jumping while only the text/numbers
    inside the live panel refresh. Older Streamlit versions safely fall back.
    """
    try:
        return st.container(height=height, border=False)
    except TypeError:
        return st.container()


def _render_live_thinking_text_only(result: Dict[str, Any]) -> None:
    """Render the live thinking card without an iframe reload.

    The old components.html path rebuilt the whole embedded box every refresh,
    which made the page feel like the entire card was jumping. This keeps the
    same visual HTML from build_live_thinking_html, but renders it directly into
    Streamlit markdown so the stable parent stays in place and only the words /
    numbers inside the card change on each fragment refresh.
    """
    html = build_live_thinking_html(result)
    style_parts = re.findall(r"<style>(.*?)</style>", html, flags=re.S | re.I)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.S | re.I)
    body = body_match.group(1) if body_match else html
    style = "\n".join(style_parts)
    st.markdown(f"<style>{style}</style>{body}", unsafe_allow_html=True)


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


def _session_elapsed_label(user_key: str, mode: str) -> str:
    raw = st.session_state.get(f"tradesmart_session_start_{user_key}_{mode}")
    if not raw:
        return "—"
    try:
        start = datetime.fromisoformat(str(raw))
        elapsed = max(0, int((datetime.now() - start).total_seconds()))
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    except Exception:
        return "—"


def _session_win_loss_label(account: Dict[str, Any]) -> str:
    wins = int(_float_value(account.get("session_wins"), 0.0))
    losses = int(_float_value(account.get("session_losses"), 0.0))
    total = wins + losses
    if total <= 0:
        return "0W / 0L"
    return f"{wins}W / {losses}L ({wins / total:.0%})"


def _normalize_symbol(value: Any) -> str:
    """Normalize broker symbols so XAUUSD, XAUUSDm, XAUUSD.pro, etc. match."""
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _symbol_matches(value: Any) -> bool:
    symbol = _normalize_symbol(value)
    wanted = _normalize_symbol(SYMBOL)
    return bool(symbol) and (symbol == wanted or symbol.startswith(wanted) or wanted in symbol)


def _parse_trade_time(value: Any) -> datetime | None:
    """Accept MT5 timestamps, ISO strings, pandas timestamps, and datetime values."""
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    try:
        # MT5 deal.time is usually epoch seconds. time_msc is milliseconds.
        if isinstance(value, (int, float)):
            number = float(value)
            if number > 10_000_000_000:
                number = number / 1000.0
            return datetime.fromtimestamp(number)
    except Exception:
        pass

    text = str(value).strip()
    if not text:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _same_or_after_session(close_time: datetime | None, session_start: datetime | None) -> bool:
    if close_time is None or session_start is None:
        # If no time was supplied by the agent snapshot, do not reject it here.
        # The MT5 direct history reader below is still the primary session filter.
        return True

    try:
        if close_time.tzinfo is not None and session_start.tzinfo is None:
            close_time = close_time.astimezone(MARKET_TZ).replace(tzinfo=None)
        elif close_time.tzinfo is None and session_start.tzinfo is not None:
            session_start = session_start.astimezone(MARKET_TZ).replace(tzinfo=None)
    except Exception:
        pass

    return close_time >= (session_start - timedelta(seconds=10))


def _collect_closed_trade_results(
    result: Dict[str, Any],
    session_start: datetime | None = None,
) -> list[Tuple[str, float]]:
    """Collect closed trades from agent snapshots, filtered to this session when time exists."""
    found: list[Tuple[str, float]] = []
    keys = (
        "closed_trades",
        "closed_positions",
        "closed_deals",
        "history_deals",
        "deal_history",
        "trade_history",
        "session_closed_trades",
        "trades",
    )
    for key in keys:
        rows = result.get(key)
        if not isinstance(rows, list):
            continue

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue

            # If a generic trades list is supplied, only count rows that are truly closed.
            if key == "trades" and not bool(row.get("closed") or row.get("is_closed") or row.get("close_time") or row.get("closeTime")):
                continue

            symbol = row.get("symbol") or row.get("instrument")
            if symbol and not _symbol_matches(symbol):
                continue

            profit_raw = (
                row.get("profit")
                if row.get("profit") not in (None, "")
                else row.get("pl", row.get("pnl", row.get("profit_loss", row.get("net_profit"))))
            )
            if profit_raw in (None, ""):
                continue

            close_time = _parse_trade_time(
                row.get("close_time")
                or row.get("closeTime")
                or row.get("closed_at")
                or row.get("time")
                or row.get("time_msc")
            )
            if not _same_or_after_session(close_time, session_start):
                continue

            ticket = (
                row.get("ticket")
                or row.get("deal")
                or row.get("order")
                or row.get("position")
                or row.get("position_id")
                or row.get("id")
                or f"{key}:{idx}:{profit_raw}:{close_time or ''}"
            )
            found.append((str(ticket), _float_value(profit_raw, 0.0)))
    return found


def _collect_mt5_session_closed_trade_results(
    user_key: str, mode: str, profile: Dict[str, Any] | None = None
) -> list[Tuple[str, float]]:
    """Read every closed TradeSmart session outcome directly from MT5 history.

    Important fix:
    - Do NOT group everything only by position_id/order, because some brokers or
      MT5 netting accounts can reuse one position/order reference for more than
      one close event. That made the page show only one win/loss.
    - Count each real closing deal ticket as its own session result.
    - Keep a conservative fallback for brokers that do not expose DEAL_ENTRY_OUT.
    """
    start_raw = st.session_state.get(f"tradesmart_session_start_{user_key}_{mode}")
    if not start_raw:
        return []

    session_start = _parse_trade_time(start_raw)
    if session_start is None:
        return []

    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        return []

    try:
        if getattr(mt5, "terminal_info", lambda: None)() is None:
            init_kwargs: Dict[str, Any] = {}
            if isinstance(profile, dict):
                if profile.get("login"):
                    init_kwargs["login"] = int(profile.get("login"))
                if profile.get("password"):
                    init_kwargs["password"] = profile.get("password")
                if profile.get("server"):
                    init_kwargs["server"] = profile.get("server")
            mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()
    except Exception:
        pass

    local_start = session_start.replace(tzinfo=None) if session_start.tzinfo else session_start
    local_end = datetime.now() + timedelta(seconds=30)

    windows: list[Tuple[datetime, datetime]] = [
        (local_start - timedelta(minutes=5), local_end),
    ]

    try:
        if session_start.tzinfo is None:
            utc_start = session_start.replace(tzinfo=MARKET_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        else:
            utc_start = session_start.astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = datetime.now(tz=timezone.utc).replace(tzinfo=None) + timedelta(seconds=30)
        windows.append((utc_start - timedelta(minutes=5), utc_end))
    except Exception:
        pass

    def _deal_value(deal: Any, name: str, default: Any = None) -> Any:
        if isinstance(deal, dict):
            return deal.get(name, default)
        return getattr(deal, name, default)

    def _deal_profit(deal: Any) -> float:
        return (
            _float_value(_deal_value(deal, "profit", 0.0), 0.0)
            + _float_value(_deal_value(deal, "swap", 0.0), 0.0)
            + _float_value(_deal_value(deal, "commission", 0.0), 0.0)
            + _float_value(_deal_value(deal, "fee", 0.0), 0.0)
        )

    entry_out_values = {
        value for value in (
            getattr(mt5, "DEAL_ENTRY_OUT", None),
            getattr(mt5, "DEAL_ENTRY_OUT_BY", None),
            getattr(mt5, "DEAL_ENTRY_INOUT", None),
        ) if value is not None
    }

    raw_deals: list[Any] = []
    seen_deal_tickets = set()

    for date_from, date_to in windows:
        for kwargs in ({}, {"group": f"*{SYMBOL}*"}, {"group": "*XAU*"}):
            try:
                deals = mt5.history_deals_get(date_from, date_to, **kwargs)
            except Exception:
                deals = None
            if not deals:
                continue

            for deal in deals:
                ticket = _deal_value(deal, "ticket")
                time_key = _deal_value(deal, "time_msc") or _deal_value(deal, "time") or ""
                dedupe_key = str(ticket) if ticket not in (None, "") else f"obj:{id(deal)}:{time_key}"
                if dedupe_key in seen_deal_tickets:
                    continue
                seen_deal_tickets.add(dedupe_key)

                symbol = _deal_value(deal, "symbol", "")
                if symbol and not _symbol_matches(symbol):
                    continue

                close_time = _parse_trade_time(_deal_value(deal, "time_msc") or _deal_value(deal, "time"))
                if not _same_or_after_session(close_time, session_start):
                    continue

                raw_deals.append(deal)

    if not raw_deals:
        return []

    closed_results: list[Tuple[str, float]] = []

    # Best path: count each real MT5 closing deal as one closed session result.
    for deal in raw_deals:
        entry = _deal_value(deal, "entry")
        if entry_out_values and entry not in entry_out_values:
            continue

        profit_piece = _deal_profit(deal)
        if abs(profit_piece) < 0.0000001:
            continue

        ticket = _deal_value(deal, "ticket")
        position_id = _deal_value(deal, "position_id")
        order = _deal_value(deal, "order")
        close_time_raw = _deal_value(deal, "time_msc") or _deal_value(deal, "time") or ""

        # Use the closing deal ticket first. This makes multiple completed
        # trades count separately even if the broker reuses a position/order id.
        trade_key = str(ticket or f"{position_id}:{order}:{close_time_raw}:{profit_piece}")
        closed_results.append((f"mt5close:{trade_key}", profit_piece))

    if closed_results:
        return closed_results

    # Broker fallback: entry markers were missing/unusable. Count every non-zero
    # booked deal after session start as its own finished result by deal ticket.
    # This is intentionally not grouped by position_id so multiple closed trades
    # cannot overwrite each other.
    for deal in raw_deals:
        profit_piece = _deal_profit(deal)
        if abs(profit_piece) < 0.0000001:
            continue

        ticket = _deal_value(deal, "ticket")
        position_id = _deal_value(deal, "position_id")
        order = _deal_value(deal, "order")
        close_time_raw = _deal_value(deal, "time_msc") or _deal_value(deal, "time") or ""
        trade_key = str(ticket or f"{position_id}:{order}:{close_time_raw}:{profit_piece}")
        closed_results.append((f"mt5deal:{trade_key}", profit_piece))

    return closed_results


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
    st.session_state[_scope_key("tradesmart_session_closed_trade_ids", user_key, mode)] = set()

    # Persist each closed trade result for this exact session. MT5 history can
    # briefly return partial windows on reruns, so keeping a session-local ledger
    # prevents wins/losses from disappearing or flipping back to 0.
    #
    # Important: preserve the ledger if Streamlit reruns this reset for the same
    # active session_id. Only a brand-new session_id is allowed to clear it.
    closed_trade_results_key = _scope_key("tradesmart_session_closed_trade_results", user_key, mode)
    existing_results = st.session_state.get(closed_trade_results_key)
    if isinstance(existing_results, dict) and existing_results.get("__session_id__") == session_id:
        ledger = existing_results
    else:
        ledger = {"__session_id__": session_id}
    st.session_state[closed_trade_results_key] = ledger
    st.session_state[_scope_key("tradesmart_session_last_finished_count", user_key, mode)] = 0
    st.session_state[_scope_key("tradesmart_session_last_closed_value", user_key, mode)] = 0.0

    wins = sum(1 for key, profit in ledger.items() if not str(key).startswith("__") and _float_value(profit, 0.0) > 0)
    losses = sum(1 for key, profit in ledger.items() if not str(key).startswith("__") and _float_value(profit, 0.0) < 0)
    st.session_state[_scope_key("tradesmart_session_wins", user_key, mode)] = wins
    st.session_state[_scope_key("tradesmart_session_losses", user_key, mode)] = losses


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
    closed_trade_ids_key = _scope_key("tradesmart_session_closed_trade_ids", user_key, mode)
    closed_trade_results_key = _scope_key("tradesmart_session_closed_trade_results", user_key, mode)
    wins_key = _scope_key("tradesmart_session_wins", user_key, mode)
    losses_key = _scope_key("tradesmart_session_losses", user_key, mode)
    last_finished_count_key = _scope_key("tradesmart_session_last_finished_count", user_key, mode)
    last_closed_value_key = _scope_key("tradesmart_session_last_closed_value", user_key, mode)

    if st.session_state.get(accounting_id_key) != session_id:
        _reset_session_accounting(user_key, mode, session_id)

    closed_today_raw = account.get("closed_pl_today")
    closed_today = _float_value(closed_today_raw, _float_value(account.get("session_closed_pl"), 0.0))
    balance_now = _float_value(account.get("balance"), 0.0)
    # Only treat this as a usable balance snapshot when MT5 actually returned a
    # real account balance. A missing/blank/zero balance usually means a
    # connect/disconnect transition or an error snapshot — never lock that in
    # as the baseline, or every later real balance reads as "all-time profit".
    has_real_balance = account.get("balance") not in (None, "") and balance_now != 0.0

    if st.session_state.get(baseline_key) is None:
        # Baseline means: everything closed before the agent session started.
        st.session_state[baseline_key] = closed_today
    if st.session_state.get(balance_baseline_key) is None and has_real_balance:
        # Balance baseline lets the page show realized P/L even if the agent does
        # not return refreshed closed_pl_today after a deal closes.
        st.session_state[balance_baseline_key] = balance_now

    closed_baseline = _float_value(st.session_state.get(baseline_key), 0.0)
    balance_baseline_raw = st.session_state.get(balance_baseline_key)
    # If we still don't have a confirmed baseline yet (e.g. very first snapshot
    # of the session hasn't landed with real MT5 data), report zero P/L instead
    # of a misleading full-balance delta.
    baseline_confirmed = balance_baseline_raw is not None
    balance_baseline = _float_value(balance_baseline_raw, balance_now)
    closed_today_delta = closed_today - closed_baseline
    balance_delta = (balance_now - balance_baseline) if (baseline_confirmed and has_real_balance) else 0.0

    # Realized session P/L: prefer balance delta because it reflects closed trades
    # immediately after MT5 books the deal. Fall back to closed_pl_today delta when
    # balance is unavailable, and fall back to 0.0 when no baseline is confirmed yet.
    if baseline_confirmed and has_real_balance:
        session_closed = balance_delta
    elif account.get("balance") not in (None, ""):
        session_closed = 0.0
    else:
        session_closed = closed_today_delta

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

    closed_trade_ids = st.session_state.get(closed_trade_ids_key)
    if not isinstance(closed_trade_ids, set):
        closed_trade_ids = set(closed_trade_ids or [])

    closed_trade_results = st.session_state.get(closed_trade_results_key)
    if not isinstance(closed_trade_results, dict) or closed_trade_results.get("__session_id__") != session_id:
        closed_trade_results = {"__session_id__": session_id}

    # Win/Loss must be based on trades CLOSED during this exact TradeSmart session.
    # Priority:
    # 1) MT5 history after session_start (best / real closed deals)
    # 2) agent-supplied closed trade arrays after session_start
    # 3) agent-supplied session_wins/session_losses if available
    # 4) safe fallback: if we have closed P/L but no broker history, infer all
    #    finished session trades from the net closed P/L direction instead of
    #    displaying the wrong 0W / 0L.
    session_start_dt = _parse_trade_time(st.session_state.get(f"tradesmart_session_start_{user_key}_{mode}"))

    # Pull BOTH sources every refresh. MT5 can sometimes compress history into
    # one net close, while the agent snapshot may still contain the individual
    # per-trade results. The old logic skipped the agent list whenever MT5
    # returned anything, which is why mixed sessions could become all losses.
    mt5_closed_results = _collect_mt5_session_closed_trade_results(
        user_key,
        mode,
        risk.get("_mt5_profile"),
    )
    agent_closed_results = _collect_closed_trade_results(result, session_start=session_start_dt)

    closed_results = []
    seen_result_keys = set()
    for trade_id, profit in list(mt5_closed_results or []) + list(agent_closed_results or []):
        result_key = str(trade_id)
        if result_key in seen_result_keys:
            continue
        seen_result_keys.add(result_key)
        closed_results.append((result_key, profit))

    # Add only newly discovered closed trades to this session's result map.
    # Then count from the persisted map, not just from the latest MT5 response.
    # This fixes the issue where wins/losses tracked "when it wanted to" because
    # one refresh could see a deal and the next refresh could miss it.
    for trade_id, profit in closed_results:
        trade_key = str(trade_id)
        profit_value = _float_value(profit, 0.0)
        if abs(profit_value) < 0.0000001:
            continue
        closed_trade_ids.add(trade_key)
        closed_trade_results[trade_key] = profit_value

    # Count from the full persisted session ledger. Never count only the latest
    # MT5 response, because the latest response can be empty/partial while the
    # session is still valid. Metadata keys are ignored.
    wins = sum(
        1
        for key, profit in closed_trade_results.items()
        if not str(key).startswith("__") and _float_value(profit, 0.0) > 0
    )
    losses = sum(
        1
        for key, profit in closed_trade_results.items()
        if not str(key).startswith("__") and _float_value(profit, 0.0) < 0
    )

    # Live lifecycle fallback: when a trade finishes, use the CHANGE in
    # Session Closed since the previous finished trade. This preserves the real
    # win/loss direction for each completed trade instead of assigning every
    # missing trade the final net session direction.
    open_now_lifecycle = int(_float_value(result.get("open_positions_count", account.get("open_positions", 0)), 0.0))
    finished_count_lifecycle = max(0, int(opened_count) - max(0, open_now_lifecycle))
    prev_finished_count = int(_float_value(st.session_state.get(last_finished_count_key), 0.0))
    prev_closed_value = _float_value(st.session_state.get(last_closed_value_key), 0.0)

    if finished_count_lifecycle > prev_finished_count:
        newly_finished = finished_count_lifecycle - prev_finished_count
        delta_closed = session_closed - prev_closed_value
        current_count = wins + losses

        # Only add lifecycle rows for trades that are still missing from the
        # ledger. If MT5/agent already gave the individual trade rows, leave
        # them alone.
        missing_now = max(0, finished_count_lifecycle - current_count)
        rows_to_add = min(newly_finished, missing_now)
        if rows_to_add > 0 and abs(delta_closed) > 0.0000001:
            per_trade_profit = delta_closed / max(1, newly_finished)
            for idx in range(rows_to_add):
                lifecycle_index = current_count + idx + 1
                lifecycle_key = f"lifecycle:{session_id}:{lifecycle_index}"
                if lifecycle_key not in closed_trade_results:
                    closed_trade_ids.add(lifecycle_key)
                    closed_trade_results[lifecycle_key] = per_trade_profit

            wins = sum(
                1
                for key, profit in closed_trade_results.items()
                if not str(key).startswith("__") and _float_value(profit, 0.0) > 0
            )
            losses = sum(
                1
                for key, profit in closed_trade_results.items()
                if not str(key).startswith("__") and _float_value(profit, 0.0) < 0
            )

    # Agent-level fallback if the agent already knows the session count.
    if wins == 0 and losses == 0:
        agent_wins = int(_float_value(account.get("session_wins", result.get("session_wins", 0)), 0.0))
        agent_losses = int(_float_value(account.get("session_losses", result.get("session_losses", 0)), 0.0))
        if agent_wins or agent_losses:
            wins = max(0, agent_wins)
            losses = max(0, agent_losses)

    # Last-resort fallback only for ONE ambiguous finished trade.
    # Do not label multiple finished trades from the net Session Closed value,
    # because a loss + win + loss + win sequence can have a negative net P/L
    # while still containing real wins.
    if wins == 0 and losses == 0:
        open_now = int(_float_value(result.get("open_positions_count", account.get("open_positions", 0)), 0.0))
        finished_count = max(0, int(opened_count) - max(0, open_now))
        if finished_count == 1 and abs(session_closed) > 0.0000001:
            fallback_key = f"fallback:{session_id}:first_finished_trade"
            closed_trade_ids.add(fallback_key)
            closed_trade_results[fallback_key] = session_closed
            if session_closed > 0:
                wins = 1
                losses = 0
            else:
                wins = 0
                losses = 1

    # Final reconciliation guard:
    # Some MT5 brokers/netting accounts return ONE net closing deal even when the
    # TradeSmart session opened/closed multiple separate trades. The page already
    # knows how many session trades finished from opened_count - open_now, so the
    # Win/Loss display must never remain below that finished count when MT5 only
    # gives a compressed/net history response.
    open_now_for_reconcile = int(_float_value(result.get("open_positions_count", account.get("open_positions", 0)), 0.0))
    finished_count_for_reconcile = max(0, int(opened_count) - max(0, open_now_for_reconcile))
    counted_count_for_reconcile = wins + losses

    if finished_count_for_reconcile > counted_count_for_reconcile and finished_count_for_reconcile > 0:
        # Do NOT force missing trades to the net session direction. That was the
        # bug that made a mixed session show as 0W / 3L. At this point we only
        # trust real per-trade rows from MT5/agent or lifecycle close deltas. If
        # the agent itself has a higher confirmed split, use it; otherwise keep
        # the accurate rows we already captured instead of inventing losses.
        agent_wins_final = int(_float_value(account.get("session_wins", result.get("session_wins", 0)), 0.0))
        agent_losses_final = int(_float_value(account.get("session_losses", result.get("session_losses", 0)), 0.0))
        if agent_wins_final + agent_losses_final >= finished_count_for_reconcile:
            wins = max(0, agent_wins_final)
            losses = max(0, agent_losses_final)

    st.session_state[last_finished_count_key] = max(
        int(_float_value(st.session_state.get(last_finished_count_key), 0.0)),
        max(0, int(opened_count) - int(_float_value(result.get("open_positions_count", account.get("open_positions", 0)), 0.0))),
    )
    st.session_state[last_closed_value_key] = session_closed

    account["session_closed_pl"] = session_closed
    account["combined_session_pl"] = combined
    account["session_baseline_closed_pl"] = closed_baseline
    account["session_balance_baseline"] = balance_baseline
    account["session_started_at"] = _session_start_label(user_key, mode)
    account["session_time_spent"] = _session_elapsed_label(user_key, mode)
    account["session_opened_trades"] = opened_count
    account["session_wins"] = wins
    account["session_losses"] = losses
    account["session_win_loss_ratio"] = _session_win_loss_label(account)

    st.session_state[session_closed_key] = session_closed
    st.session_state[session_combined_key] = combined
    st.session_state[opened_tickets_key] = opened_tickets
    st.session_state[opened_count_key] = opened_count
    st.session_state[closed_trade_ids_key] = closed_trade_ids
    st.session_state[closed_trade_results_key] = closed_trade_results
    st.session_state[wins_key] = wins
    st.session_state[losses_key] = losses

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

    # Last compatible fallback: snapshot only. Never run a live execution cycle from
    # the stop/risk-lock path, because that can place an accidental new trade.
    try:
        result = agent.run_cycle(execution_enabled=False)
        if isinstance(result, dict):
            result["agent_off"] = True
            result["phase"] = "stopped"
            result["event"] = "Emergency Close Snapshot"
            result["message"] = "Stop snapshot captured. No live execution cycle was run."
            result["decision"] = {"action": "OFF", "reason": reason}
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


def _engage_risk_lock(agent_key: str, risk: Dict[str, Any], reason: str) -> None:
    """Hard-lock the page so execution cannot continue until the user reviews it.
    This intentionally does NOT auto-clear on the next rerun. The user must press
    the clear/unlock button, then manually toggle the agent back ON.
    """
    st.session_state[agent_key] = False
    st.session_state[f"tradesmart_prev_enabled_{risk.get('user_key')}_{risk.get('mode')}"] = False
    st.session_state[_scope_key("tradesmart_force_stop_key")] = agent_key
    st.session_state[_scope_key("tradesmart_force_stopped")] = True
    st.session_state[_scope_key("tradesmart_force_stop_reason")] = reason


# ══════════════════════════════════════════════
#  LIVE SUMMARY — only render when agent is ON
#  When agent is OFF this section is replaced by
#  the _build_off_session_html card (no duplicate).
# ══════════════════════════════════════════════

def _render_live_summary(result: Dict[str, Any], agent_on: bool) -> None:
    """
    Render the live tracking grid.
    Only called when the agent is running — the OFF card already shows these.
    Uses ts-live-value class for subtle CSS transitions on each refresh.
    """
    if not agent_on:
        return

    result  = result or {}
    account = result.get("account") or {}

    st.markdown(
        '<div class="ts-live-summary-title">Live Tracking Summary</div>',
        unsafe_allow_html=True,
    )

    def _color_class(val: Any) -> str:
        try:
            v = float(val or 0)
            if v > 0:
                return "ts-pos"
            if v < 0:
                return "ts-neg"
        except Exception:
            pass
        return ""

    def _m(label: str, raw: Any, money: bool = False) -> str:
        display = _money(raw) if money else escape(str(raw if raw not in (None, "") else "—"))
        cc = _color_class(raw) if money else ""
        return (
            f"<div class='ts-metric'>"
            f"<div class='ts-metric-label'>{escape(label)}</div>"
            f"<div class='ts-metric-value ts-live-value {cc}'>{display}</div>"
            f"</div>"
        )

    balance    = account.get("balance")
    equity     = account.get("equity")
    float_pl   = account.get("floating_pl")
    sess_cl    = account.get("session_closed_pl")
    sess_total = account.get("combined_session_pl")
    open_cnt   = result.get("open_positions_count", account.get("open_positions", 0))
    started    = account.get("session_started_at") or result.get("session_started_at") or "Not started"
    session_opened = result.get("session_opened_trades", account.get("session_opened_trades", 0))
    win_loss = account.get("session_win_loss_ratio") or _session_win_loss_label(account)

    html = "<div class='ts-summary'>" + "".join([
        _m("Balance",        balance,     money=True),
        _m("Equity",         equity,      money=True),
        _m("Floating P/L",   float_pl,    money=True),
        _m("Session Closed", sess_cl,     money=True),
        _m("Session P/L",    sess_total,  money=True),
        _m("Open Trades",    open_cnt),
        _m("Session Start",  started),
        _m("Win/Loss",       win_loss),
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
    result = _apply_session_accounting(result, {**risk, "_mt5_profile": profile})
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
    time_spent  = account.get("session_time_spent") or _session_elapsed_label(_user_key(), mode)
    win_loss    = account.get("session_win_loss_ratio") or _session_win_loss_label(account)
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
    <div class='ts-box'><div class='ts-label'>Time Spent</div><div class='ts-value'>{_plain(time_spent)}</div></div>
    <div class='ts-box'><div class='ts-label'>Win/Loss</div><div class='ts-value'>{_plain(win_loss)}</div></div>
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
    result = _apply_session_accounting(result, {**risk, "_mt5_profile": profile})
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
        _engage_risk_lock(agent_key, risk, market_reason)
        result = (
            _run_final_session_snapshot(profile, risk, market_reason)
            if bool(risk.get("connected"))
            else _stopped_result(risk.get("mode", "Demo"), market_reason, risk)
        )
        st.session_state[_scope_key("tradesmart_last_result")] = result
        _add_log("Market Closed", market_reason, result)
        enabled = False
        st.rerun()

    # ── Agent ON — run live cycle ─────────────────────────────────
    elif enabled:
        # Pre-flight risk gate. This runs BEFORE the agent is allowed to execute,
        # so lowering risk settings or carrying a breached floating/closed loss
        # cannot allow one final trade to slip in on the next refresh.
        pre_risk_hit, pre_risk_msg = _page_risk_breached(result, risk)
        if pre_risk_hit:
            stop_msg = pre_risk_msg or "Max session risk reached before execution."
            close_result = _emergency_flatten_positions(profile, risk, stop_msg)
            _add_log(
                close_result.get("event", "Emergency Close"),
                close_result.get("message", "Risk lock attempted to close open positions before another cycle."),
                close_result,
            )
            final = _run_final_session_snapshot(profile, risk, stop_msg)
            _engage_risk_lock(agent_key, risk, stop_msg)
            result = final
            enabled = False
            st.session_state[_scope_key("tradesmart_last_result")] = result
            st.rerun()
        else:
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
                final = _run_final_session_snapshot(profile, risk, stop_msg)
                _engage_risk_lock(agent_key, risk, stop_msg)
                result = final
                enabled = False
                st.session_state[_scope_key("tradesmart_last_result")] = result
                st.rerun()

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
        # Live thinking card (auto-refreshed by the fragment).
        # Render directly instead of iframe components.html so the outer box stays
        # stable and only the visible words/numbers update on refresh.
        _render_live_thinking_text_only(result)
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
    c1, c2, c3 = st.columns(3)
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
    min_score = 0.75  # Fixed production filter: TradeSmart only executes 75%+ setups.

    risk = {
        "mode":                   mode,
        "trade_volume":           trade_volume,
        "volume":                 trade_volume,          # alias agents expect
        "max_open_trades":        int(max_open),
        "max_daily_loss_amount":  float(max_loss),
        "min_strategy_score":     0.75,
        "market_open":            bool(market_open),
        "market_reason":          market_reason,
        "user_key":               user_key,
        "user_id":                _safe_user_id(user_key),
        "output_scope":           f"{_safe_user_id(user_key)}_{mode.lower()}",
        "connected":              bool(connected),
        "trade_cooldown_seconds": 10,
        # Will be overridden below after toggle state is resolved
        "agent_off":              False,
    }

    # These flags are resolved after the toggle state block below.
    # Placeholder so the dict key exists for the disabled= parameter check.
    risk["risk_lock_active"] = bool(st.session_state.get(_scope_key("tradesmart_force_stopped")))
    risk["execution_blocked"] = bool(risk["risk_lock_active"])

    # ── CONNECTION + AGENT CONTROL ────────────────────────────────
    _section("Connection + Live Agent Control")
    agent_key = f"tradesmart_agent_enabled_{user_key}_{mode}"

    # Risk lock must persist until the user reviews and clears it.
    # Do not auto-clear this flag on rerun, or the toggle can visually recover too early.
    risk_lock_active = bool(st.session_state.get(_scope_key("tradesmart_force_stopped")))
    if st.session_state.get(_scope_key("tradesmart_force_stop_key")) == agent_key:
        st.session_state[agent_key] = False
        st.session_state[f"tradesmart_prev_enabled_{user_key}_{mode}"] = False
        risk_lock_active = True

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
            disabled=(not complete or not connected or not market_open or risk_lock_active),
        )
        if (not market_open or risk_lock_active) and current_enabled:
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
            if st.button("Unlock after review", help="Clears the risk lock. You still need to manually toggle the agent ON again."):
                st.session_state[_scope_key("tradesmart_force_stopped")] = False
                st.session_state.pop(_scope_key("tradesmart_force_stop_reason"), None)
                st.session_state.pop(_scope_key("tradesmart_force_stop_key"), None)
                risk_lock_active = False
                risk["risk_lock_active"] = False
                risk["execution_blocked"] = False
                st.rerun()

    # ── RISK SESSION + MANUAL OFF SNAPSHOT ───────────────────────
    prev_before_toggle = bool(
        st.session_state.get(f"tradesmart_prev_enabled_{user_key}_{mode}", False)
    )
    risk["risk_session_id"] = _ensure_risk_session(user_key, mode, enabled)

    # Sync the definitive agent_off flag now that toggle state is resolved
    risk["agent_off"] = not enabled
    risk["risk_lock_active"] = bool(st.session_state.get(_scope_key("tradesmart_force_stopped")))
    risk["execution_blocked"] = bool(risk["risk_lock_active"] or not enabled)

    # User just toggled OFF → do NOT close trades. Manual OFF only pauses execution
    # and captures a clean snapshot. Open trades stay open unless the stop reason is
    # a risk breach, which is handled inside the risk-lock branches above.
    manual_off_event = bool(connected and prev_before_toggle and not enabled)
    if manual_off_event:
        final_result = _run_final_session_snapshot(
            profile, risk,
            "Agent is OFF. Open trades were left open; session totals captured at stop.",
        )
        st.session_state[_scope_key("tradesmart_last_result")] = final_result
        _add_log(
            "Session Snapshot",
            "Agent manually stopped. Open trades were left open and final session totals were captured.",
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

    live_height = 735 if enabled else 325
    with _stable_container(live_height):
        if enabled and hasattr(st, "fragment"):
            # Fragment ONLY created when agent is ON — stops auto-refresh when OFF.
            # The fixed-height parent keeps the page stable, so only the visible
            # words/numbers change instead of the screen jumping around.
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
