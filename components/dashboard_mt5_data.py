from __future__ import annotations

from datetime import datetime, timedelta

SYMBOL = "XAUUSD"


def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def _as_dict(obj):
    if obj is None:
        return {}
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())
    if isinstance(obj, dict):
        return obj
    return {}


def _money(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _format_time(value):
    try:
        ts = int(value or 0)
        if ts > 10_000_000_000:
            ts //= 1000
        if ts <= 0:
            return "—"
        return datetime.fromtimestamp(ts).strftime("%b %d, %Y • %I:%M:%S %p")
    except Exception:
        return "—"


def _ensure_mt5_ready(mt5):
    """Read from the current MT5 session only.

    Dashboard data should never launch/open MT5 by itself. The selected
    Demo/Live account is connected upstream only when the user presses
    Connect / Read Account. This keeps the dashboard fast and prevents
    Streamlit reruns from freezing while MT5 starts.
    """
    try:
        return mt5.account_info() is not None
    except Exception:
        return False


def _position_direction(mt5_type):
    try:
        typ = int(mt5_type or 0)
    except Exception:
        typ = 0
    return "BUY" if typ == 0 else "SELL" if typ == 1 else "—"


def _deal_direction(mt5_type):
    try:
        typ = int(mt5_type or 0)
    except Exception:
        typ = 0
    return "BUY" if typ == 0 else "SELL" if typ == 1 else "—"


def get_live_mt5_dashboard_data(symbol=SYMBOL, days_back=90, mode_label=None):
    """
    Read live MT5 data for the given symbol.

    mode_label: optional string ("Demo" / "Live") describing which saved
    profile was connected before this call. Purely cosmetic — echoed back
    in the result dict so the UI can show which account is active. Does not
    affect the MT5 read itself, since connection/mode switching happens
    upstream via mt5_secure_store.connect_mt5(profile).
    """
    empty = {
        "online": False,
        "symbol": symbol,
        "mode": mode_label,
        "account": {
            "login": "—",
            "server": "—",
            "balance": 0.0,
            "equity": 0.0,
            "currency": "—",
        },
        "open_positions": [],
        "last_10_trades": [],
        "metrics": {
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "open_positions": 0,
            "open_profit": 0.0,
        },
    }

    mt5 = _import_mt5()
    if mt5 is None:
        return empty

    try:
        if not _ensure_mt5_ready(mt5):
            return empty

        account_info = mt5.account_info()
        if account_info is None:
            return empty

        account = _as_dict(account_info)

        raw_positions = mt5.positions_get(symbol=symbol)
        positions = []
        open_profit = 0.0

        for pos in list(raw_positions or []):
            x = _as_dict(pos)
            profit = _money(x.get("profit")) + _money(x.get("swap")) + _money(x.get("commission"))
            open_profit += profit
            positions.append({
                "Ticket": x.get("ticket", "—"),
                "Symbol": x.get("symbol", symbol),
                "Direction": _position_direction(x.get("type")),
                "Volume": x.get("volume", 0),
                "Open Price": x.get("price_open", 0),
                "Current Price": x.get("price_current", 0),
                "Profit": round(profit, 2),
                "Opened": _format_time(x.get("time")),
                "_ts": int(x.get("time", 0) or 0),
            })

        positions.sort(key=lambda row: row.get("_ts", 0), reverse=True)
        for row in positions:
            row.pop("_ts", None)

        now = datetime.now()
        start = now - timedelta(days=days_back)
        raw_deals = mt5.history_deals_get(start, now)

        closed_deals = []
        all_deals_for_metrics = []

        for deal in list(raw_deals or []):
            x = _as_dict(deal)

            if str(x.get("symbol", "")).upper() != symbol.upper():
                continue

            profit = _money(x.get("profit")) + _money(x.get("swap")) + _money(x.get("commission"))
            entry = x.get("entry")

            # MT5 entry 1/2 are closing/out deals. If entry is missing, keep real P/L deals only.
            if entry not in (1, 2) and abs(profit) < 0.0000001:
                continue

            ts = int(x.get("time", 0) or 0)
            row = {
                "Closed": _format_time(ts),
                "Ticket": x.get("ticket", "—"),
                "Order": x.get("order", "—"),
                "Symbol": x.get("symbol", symbol),
                "Direction": _deal_direction(x.get("type")),
                "Volume": x.get("volume", 0),
                "Price": x.get("price", 0),
                "Profit": round(profit, 2),
                "Comment": x.get("comment", ""),
                "_ts": ts,
            }
            all_deals_for_metrics.append(row)
            closed_deals.append(row)

        closed_deals.sort(key=lambda row: row.get("_ts", 0), reverse=True)
        all_deals_for_metrics.sort(key=lambda row: row.get("_ts", 0), reverse=True)

        today = datetime(now.year, now.month, now.day)
        week = today - timedelta(days=today.weekday())
        month = datetime(now.year, now.month, 1)

        def pnl_since(dt):
            threshold = int(dt.timestamp())
            return round(sum(_money(row.get("Profit")) for row in all_deals_for_metrics if int(row.get("_ts", 0)) >= threshold), 2)

        wins = sum(1 for row in all_deals_for_metrics if _money(row.get("Profit")) > 0)
        losses = sum(1 for row in all_deals_for_metrics if _money(row.get("Profit")) < 0)
        closed_count = len(all_deals_for_metrics)

        last_10 = []
        for row in closed_deals[:10]:
            clean = dict(row)
            clean.pop("_ts", None)
            last_10.append(clean)

        return {
            "online": True,
            "symbol": symbol,
            "mode": mode_label,
            "account": {
                "login": account.get("login", "—"),
                "server": account.get("server", "—"),
                "balance": round(_money(account.get("balance")), 2),
                "equity": round(_money(account.get("equity")), 2),
                "currency": account.get("currency", "—"),
            },
            "open_positions": positions,
            "last_10_trades": last_10,
            "metrics": {
                "daily_pnl": pnl_since(today),
                "weekly_pnl": pnl_since(week),
                "monthly_pnl": pnl_since(month),
                "total_pnl": round(sum(_money(row.get("Profit")) for row in all_deals_for_metrics), 2),
                "win_rate": round((wins / closed_count) * 100, 1) if closed_count else 0.0,
                "closed_trades": closed_count,
                "wins": wins,
                "losses": losses,
                "open_positions": len(positions),
                "open_profit": round(open_profit, 2),
            },
        }

    except Exception as exc:
        empty["error"] = str(exc)
        return empty
