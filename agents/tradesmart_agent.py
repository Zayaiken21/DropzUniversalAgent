from __future__ import annotations

import importlib.util
import json
import time
import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

SYMBOL_DEFAULT = "XAUUSD"
MAGIC = 777001
MARKET_TZ = ZoneInfo("America/New_York")


def _safe_user_id(value: Any) -> str:
    """Filesystem/session safe user id for TradeSmart isolation.

    Kept local to this module so the agent does not depend on the Streamlit
    page helper being imported. This prevents NameError when the agent is
    constructed from connect/disconnect buttons, scheduled scans, or tests.
    """
    raw = str(value or "default")
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")[:64]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{clean or 'user'}_{digest}"


class TradeSmartAgent:
    """Lean execution controller.

    The page owns the 3-second loop and toggle state. Strategies own market
    logic. This agent only connects MT5, loads strategies, combines strategy
    scores, applies risk settings passed by the page, places/closes orders, and
    returns structured thinking output.
    """

    def __init__(self, profile: Dict[str, Any] | None = None, rules: Dict[str, Any] | None = None):
        self.profile = dict(profile or {})
        self.rules = dict(rules or {})
        self.symbol = str(self.rules.get("symbol") or self.profile.get("symbol") or SYMBOL_DEFAULT)
        self.project_root = Path(__file__).resolve().parents[1]
        self.user_key = str(self.rules.get("user_key") or self.profile.get("user_key") or "default")
        self.user_id = _safe_user_id(self.rules.get("user_id") or self.user_key)
        self.output_scope = str(self.rules.get("output_scope") or f"{self.user_id}_{str(self.rules.get('mode') or self.profile.get('mode') or 'Demo').lower()}")
        self.data_dir = self.project_root / "data" / "users" / self.user_id / "tradesmart"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "tradesmart_agent_state.json"

    # MT5 connection
    def _mt5(self):
        try:
            import platform
            if platform.system() != "Windows":
                return None, "MetaTrader5 direct mode is only available on Windows."
            import MetaTrader5 as mt5
            return mt5, None
        except Exception as exc:
            return None, f"MetaTrader5 not available: {exc}"

    def _connect(self) -> Tuple[bool, str, Optional[Dict[str, Any]], Any]:
        profile = dict(self.profile or {})
        profile["mode"] = str(self.rules.get("mode") or profile.get("mode") or "Demo").title()
        profile["symbol"] = self.symbol
        profile["user_key"] = self.user_key
        profile["user_id"] = self.user_id
        # Prefer your existing secure-store connector if present, so Demo/Live
        # saved Settings keep working exactly the same.
        try:
            from frontend.mt5_secure_store import connect_mt5
            ok, message, account = connect_mt5(profile)
            mt5, _ = self._mt5()
            return bool(ok), str(message), account if isinstance(account, dict) else (account._asdict() if account else None), mt5
        except Exception:
            pass
        mt5, error = self._mt5()
        if error:
            return False, error, None, None
        login = profile.get("login")
        password = profile.get("password")
        server = profile.get("server")
        terminal_path = profile.get("terminal_path") or profile.get("path") or None
        timeout = min(int(profile.get("timeout", 12000) or 12000), 15000)
        portable = bool(profile.get("portable", False))
        if not login or not password or not server:
            return False, "Missing MT5 login, password, or server.", None, mt5
        try:
            mt5.shutdown()
        except Exception:
            pass
        try:
            init_kwargs = {"timeout": timeout, "portable": portable}
            ok = mt5.initialize(path=str(terminal_path), **init_kwargs) if terminal_path else mt5.initialize(**init_kwargs)
        except Exception as exc:
            return False, f"MT5 initialize error: {exc}", None, mt5
        if not ok:
            return False, f"MT5 init failed: {mt5.last_error()}", None, mt5
        try:
            login_ok = mt5.login(int(str(login).strip()), password=str(password), server=str(server).strip(), timeout=timeout)
        except Exception as exc:
            login_ok = False
            last_err = f"MT5 login exception: {exc}"
        else:
            last_err = mt5.last_error()
        account = mt5.account_info()
        if not login_ok and account is None:
            return False, f"MT5 login failed for {login}: {last_err}", None, mt5
        data = account._asdict() if account is not None else {}
        if str(data.get("login", "")).strip() and str(data.get("login", "")).strip() != str(login).strip():
            mt5.shutdown()
            return False, f"Wrong account. Expected {login}, got {data.get('login')}.", None, mt5
        return True, "Connected to MT5 successfully.", data, mt5

    def disconnect(self) -> None:
        mt5, error = self._mt5()
        if not error and mt5 is not None:
            try:
                mt5.shutdown()
            except Exception:
                pass

    # Converters/data
    def _native(self, value: Any) -> Any:
        try:
            if hasattr(value, "item"):
                return value.item()
        except Exception:
            pass
        return round(value, 6) if isinstance(value, float) else value

    def _row(self, row: Any, parent: Any = None) -> Dict[str, Any]:
        if hasattr(row, "_asdict"):
            return {str(k): self._native(v) for k, v in row._asdict().items()}
        if isinstance(row, dict):
            return {str(k): self._native(v) for k, v in row.items()}
        names = getattr(getattr(row, "dtype", None), "names", None) or getattr(getattr(parent, "dtype", None), "names", None)
        if names:
            return {str(n): self._native(row[n]) for n in names}
        return {}

    def _rates_tf(self, mt5: Any, timeframe: Any, count: int) -> List[Dict[str, Any]]:
        try:
            raw = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
        except Exception:
            return []
        if raw is None:
            return []
        rows = [self._row(r, raw) for r in raw]
        rows = [r for r in rows if r]
        rows.sort(key=lambda x: int(x.get("time", 0) or 0))
        return rows

    def _rates_multi(self, mt5: Any) -> Dict[str, List[Dict[str, Any]]]:
        tf_map = {
            "M1": (getattr(mt5, "TIMEFRAME_M1", None), 360),
            "M5": (getattr(mt5, "TIMEFRAME_M5", None), 240),
            "M15": (getattr(mt5, "TIMEFRAME_M15", None), 180),
            "H1": (getattr(mt5, "TIMEFRAME_H1", None), 140),
            "H4": (getattr(mt5, "TIMEFRAME_H4", None), 90),
            "D1": (getattr(mt5, "TIMEFRAME_D1", None), 45),
        }
        out: Dict[str, List[Dict[str, Any]]] = {}
        for tf, (const, count) in tf_map.items():
            if const is not None:
                rows = self._rates_tf(mt5, const, count)
                if rows:
                    out[tf] = rows
        return out

    def _positions(self, mt5: Any) -> List[Dict[str, Any]]:
        try:
            raw = mt5.positions_get(symbol=self.symbol)
        except Exception:
            raw = None
        if raw is None:
            return []
        out: List[Dict[str, Any]] = []
        for pos in raw:
            data = self._row(pos)
            if int(data.get("magic", 0) or 0) == MAGIC or "TradeSmart" in str(data.get("comment", "")):
                out.append(data)
        return out

    def _account_snapshot(self, account: Dict[str, Any], positions: List[Dict[str, Any]], closed_pl: float, session_closed_pl: float | None = None) -> Dict[str, Any]:
        balance = float(account.get("balance", 0) or 0)
        equity = float(account.get("equity", balance) or balance)
        floating = sum(float(p.get("profit", 0) or 0) for p in positions)
        session_closed = closed_pl if session_closed_pl is None else float(session_closed_pl or 0.0)
        return {
            "login": account.get("login"),
            "server": account.get("server"),
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "currency": account.get("currency"),
            "leverage": account.get("leverage"),
            "open_positions": len(positions),
            "floating_pl": round(floating, 2),
            "closed_pl_today": round(closed_pl, 2),
            "session_closed_pl": round(session_closed, 2),
            "combined_daily_pl": round(closed_pl + floating, 2),
            "combined_session_pl": round(session_closed + floating, 2),
        }

    def _risk_session_pl(self, closed_pl_today: float) -> Tuple[str, float, float]:
        """Return (risk_session_id, baseline_closed_pl, session_closed_delta).

        Every manual toggle-on from the TradeSmart page sends a new risk_session_id.
        The first scan of that session stores today's already-closed TradeSmart P/L as
        the baseline, so old losses do not instantly trigger the max-loss kill switch.
        The max loss then watches: floating P/L + closed P/L since this toggle-on.
        """
        session_id = str(self.rules.get("risk_session_id") or self._state_key())
        state = self._load_state()
        key = self._state_key()
        bucket = state.setdefault(key, {})
        current = bucket.get("risk_session_id")
        if current != session_id or "risk_baseline_closed_pl" not in bucket:
            bucket["risk_session_id"] = session_id
            bucket["risk_baseline_closed_pl"] = float(closed_pl_today or 0.0)
            bucket["risk_session_started"] = time.time()
            bucket.pop("risk_locked", None)
            bucket.pop("risk_lock_reason", None)
            self._save_state(state)
        baseline = float(bucket.get("risk_baseline_closed_pl", 0.0) or 0.0)
        return session_id, baseline, round(float(closed_pl_today or 0.0) - baseline, 2)

    def _closed_pl_today(self, mt5: Any) -> float:
        try:
            now = datetime.now(timezone.utc)
            start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            deals = mt5.history_deals_get(start, now + timedelta(minutes=1))
            if deals is None:
                return 0.0
            total = 0.0
            for deal in deals:
                d = self._row(deal)
                if str(d.get("symbol", "")) == self.symbol and (int(d.get("magic", 0) or 0) == MAGIC or "TradeSmart" in str(d.get("comment", ""))):
                    total += float(d.get("profit", 0) or 0) + float(d.get("commission", 0) or 0) + float(d.get("swap", 0) or 0)
            return round(total, 2)
        except Exception:
            return 0.0

    # Strategy loading/decision
    def _load_strategies(self) -> List[Any]:
        core = self.project_root / "strategies" / "core" / "__init__.py"
        if not core.exists():
            return []
        spec = importlib.util.spec_from_file_location("tradesmart_strategy_core", str(core))
        if not spec or not spec.loader:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        loader = getattr(mod, "load_enabled_strategies", None)
        if not callable(loader):
            return []
        loaded = loader(project_root=self.project_root)
        return loaded if isinstance(loaded, list) else []

    def _strategy_context(self, rates: Dict[str, List[Dict[str, Any]]], positions: List[Dict[str, Any]], account: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframes": rates,
            "rates": rates.get("M1", []),
            "rates_m1": rates.get("M1", []),
            "rates_m5": rates.get("M5", []),
            "rates_m15": rates.get("M15", []),
            "rates_h1": rates.get("H1", []),
            "rates_h4": rates.get("H4", []),
            "rates_d1": rates.get("D1", []),
            "positions": positions,
            "account": account,
            "rules": self.rules,
            "risk": self.rules,
            "now": datetime.now(timezone.utc).isoformat(),
            "user_key": self.user_key,
            "user_id": self.user_id,
            "output_scope": self.output_scope,
        }

    def _choose_signal(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        strategies = self._load_strategies()
        evaluated: List[Dict[str, Any]] = []
        best: Optional[Dict[str, Any]] = None
        for strategy in strategies:
            name = str(getattr(strategy, "name", strategy.__class__.__name__))
            try:
                raw = strategy.evaluate(context) or {}
            except Exception as exc:
                evaluated.append({"name": name, "action": "ERROR", "score": 0, "reason": str(exc)})
                continue
            action = str(raw.get("action") or raw.get("signal") or "NONE").upper()
            score = float(raw.get("score", raw.get("confidence", 0)) or 0)
            reason = str(raw.get("reason") or raw.get("thought") or "No reason.")
            row = {"name": name, "action": action, "score": round(score, 2), "reason": reason, "raw": raw}
            evaluated.append(row)
            if best is None or score > float(best.get("score", 0)):
                best = row
        if best is None:
            best = {"name": "none", "action": "SCAN", "score": 0.0, "reason": "No enabled strategies found.", "raw": {"action": "SCAN", "reason": "No enabled strategies found."}}
        raw = best.get("raw") if isinstance(best.get("raw"), dict) else {}
        decision = {
            "action": str(raw.get("action") or best.get("action") or "SCAN").upper(),
            "score": float(raw.get("score", best.get("score", 0)) or 0),
            "confidence": float(raw.get("confidence", raw.get("score", best.get("score", 0))) or 0),
            "reason": str(raw.get("reason") or best.get("reason") or "Scanning."),
            "sl": raw.get("sl"),
            "tp": raw.get("tp"),
            "entry": raw.get("entry"),
            "entry_candle_time": raw.get("entry_candle_time"),
            "close_ticket": raw.get("close_ticket"),
            "data": raw.get("data") or {},
            "draw_commands": raw.get("draw_commands") or [],
        }
        return decision, {"winner": best.get("name"), "evaluated": evaluated, "loaded_count": len(strategies), "raw": raw}

    # Risk/order helpers
    def _max_open(self) -> int:
        return max(1, int(float(self.rules.get("max_open_trades", 1) or 1)))

    def _volume(self, decision: Dict[str, Any]) -> float:
        return round(float(self.rules.get("trade_volume") or self.rules.get("volume") or decision.get("volume") or 0.01), 2)

    def _state_key(self) -> str:
        return f"{self.user_id}:{self.profile.get('login','unknown')}:{self.rules.get('mode', self.profile.get('mode','Demo'))}:{self.symbol}"

    def _load_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else {}
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        except Exception:
            pass

    def _dedup_ok(self, decision: Dict[str, Any]) -> bool:
        entry_time = decision.get("entry_candle_time")
        if not entry_time:
            return True
        state = self._load_state()
        key = self._state_key()
        last = ((state.get(key) or {}).get("last_entry_candle_time"))
        return str(last) != str(entry_time)

    def _mark_entry(self, decision: Dict[str, Any]) -> None:
        entry_time = decision.get("entry_candle_time")
        if not entry_time:
            return
        state = self._load_state()
        key = self._state_key()
        state.setdefault(key, {})["last_entry_candle_time"] = entry_time
        state[key]["updated"] = time.time()
        self._save_state(state)

    def _close_position(self, mt5: Any, pos: Dict[str, Any], reason: str = "TradeSmart close") -> Dict[str, Any]:
        tick = mt5.symbol_info_tick(self.symbol)
        pos_type = int(pos.get("type", 0) or 0)
        order_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(pos.get("volume", 0.01) or 0.01),
            "type": order_type,
            "position": int(pos.get("ticket")),
            "price": price,
            "deviation": int(self.rules.get("deviation", 30) or 30),
            "magic": MAGIC,
            "comment": reason[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        return res._asdict() if hasattr(res, "_asdict") else {"raw": str(res)}

    def _close_all(self, mt5: Any, positions: List[Dict[str, Any]], reason: str) -> List[Dict[str, Any]]:
        results = []
        for pos in positions:
            results.append(self._close_position(mt5, pos, reason=reason))
        return results

    def _send_order(self, mt5: Any, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Send a market order with broker-safe SL/TP validation.

        Retcode 10016 is usually MT5's "invalid stops" response. The
        strategy can correctly identify a premium/discount event, but the
        live bid/ask may move after the candle closes. Before sending, this
        normalizes SL/TP around the actual live tick, respects the broker stop
        distance, and runs order_check when available so TradeSmart blocks bad
        requests before they become confusing rejected orders.
        """
        action = str(decision.get("action", "")).upper()
        if action not in ("BUY", "SELL"):
            return {"ok": False, "message": "No buy/sell action."}

        info = mt5.symbol_info(self.symbol)
        if info is None:
            return {"ok": False, "message": f"Symbol info unavailable for {self.symbol}."}
        if not getattr(info, "visible", True):
            mt5.symbol_select(self.symbol, True)
            info = mt5.symbol_info(self.symbol) or info

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "message": "No MT5 tick available."}

        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if action == "BUY" else tick.bid)
        point = float(getattr(info, "point", 0.01) or 0.01)
        digits = int(getattr(info, "digits", 2) or 2)
        spread = abs(float(getattr(tick, "ask", price) or price) - float(getattr(tick, "bid", price) or price))
        stops_level = float(getattr(info, "trade_stops_level", 0) or 0) * point
        freeze_level = float(getattr(info, "trade_freeze_level", 0) or 0) * point
        # XAUUSD brokers often need a practical floor even when stops_level is 0.
        min_stop = max(stops_level, freeze_level, spread * 2.0, point * 50.0, 0.50)

        def r(v: float) -> float:
            return round(float(v), digits)

        sl_raw = float(decision.get("sl") or 0.0)
        tp_raw = float(decision.get("tp") or 0.0)
        adjusted = False

        if action == "BUY":
            if sl_raw <= 0 or sl_raw >= price - min_stop:
                sl_raw = price - min_stop
                adjusted = True
            risk = max(price - sl_raw, min_stop)
            if tp_raw <= 0 or tp_raw <= price + min_stop:
                tp_raw = price + (risk * 2.0)
                adjusted = True
        else:
            if sl_raw <= 0 or sl_raw <= price + min_stop:
                sl_raw = price + min_stop
                adjusted = True
            risk = max(sl_raw - price, min_stop)
            if tp_raw <= 0 or tp_raw >= price - min_stop:
                tp_raw = price - (risk * 2.0)
                adjusted = True

        sl = r(sl_raw)
        tp = r(tp_raw)
        price = r(price)

        # Final hard validation before MT5 receives the request.
        if action == "BUY" and not (sl < price and tp > price):
            return {"ok": False, "message": "Trade blocked before send: BUY SL/TP are not valid around live ask.", "price": price, "sl": sl, "tp": tp}
        if action == "SELL" and not (sl > price and tp < price):
            return {"ok": False, "message": "Trade blocked before send: SELL SL/TP are not valid around live bid.", "price": price, "sl": sl, "tp": tp}

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self._volume(decision),
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": int(self.rules.get("deviation", 50) or 50),
            "magic": MAGIC,
            "comment": "TradeSmart Agent",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        check_data = None
        try:
            check = mt5.order_check(req)
            check_data = check._asdict() if hasattr(check, "_asdict") else {"raw": str(check)}
            check_retcode = check_data.get("retcode")
            # 0 is common for successful order_check; some brokers return DONE/PLACED constants.
            valid_check_codes = {0, getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008)}
            if check_retcode not in valid_check_codes:
                return {
                    "ok": False,
                    "message": f"Trade blocked by MT5 pre-check: retcode {check_retcode}",
                    "request": req,
                    "order_check": check_data,
                    "stops_adjusted": adjusted,
                    "min_stop_distance": round(min_stop, digits),
                }
        except Exception as exc:
            check_data = {"warning": f"order_check unavailable: {exc}"}

        res = mt5.order_send(req)
        data = res._asdict() if hasattr(res, "_asdict") else {"raw": str(res)}
        retcode = data.get("retcode")
        data["ok"] = retcode in (getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008))
        data.setdefault("message", f"retcode {retcode}")
        data["request"] = req
        data["order_check"] = check_data
        data["stops_adjusted"] = adjusted
        data["min_stop_distance"] = round(min_stop, digits)
        if retcode == 10016:
            data["message"] = f"retcode 10016 invalid stops blocked by broker. Sent price {price}, SL {sl}, TP {tp}, min distance {round(min_stop, digits)}."
        return data


    def _market_status(self) -> Tuple[bool, str, str]:
        """Gold/XAUUSD daily maintenance guard in Eastern time.

        Prevents sending market orders during the common 5:00 PM-6:00 PM ET
        rollover window and weekend closures, which avoids MT5 retcode 10016
        from trying to execute while the market is closed.
        """
        et = datetime.now(tz=MARKET_TZ)
        wd = et.weekday()
        mins = et.hour * 60 + et.minute
        if wd == 5:
            return False, "Weekend market closure. Gold reopens Sunday 6:00 PM Eastern.", et.isoformat(timespec="seconds")
        if wd == 6 and mins < 18 * 60:
            return False, "Weekend market closure. Gold reopens Sunday 6:00 PM Eastern.", et.isoformat(timespec="seconds")
        if wd == 4 and mins >= 17 * 60:
            return False, "Friday market closure after 5:00 PM Eastern.", et.isoformat(timespec="seconds")
        if 17 * 60 <= mins < 18 * 60:
            return False, "Daily gold rollover: market is closed from 5:00 PM to 6:00 PM Eastern.", et.isoformat(timespec="seconds")
        return True, "Market open for TradeSmart execution.", et.isoformat(timespec="seconds")


    def _fresh_account_state(self, mt5: Any, account: Dict[str, Any], closed_pl_fallback: float | None = None) -> Tuple[List[Dict[str, Any]], float, float, Dict[str, Any]]:
        """Refresh positions and P/L after closes/orders.

        MT5 position/deal state can change between cycles or immediately after a
        close. This keeps the page's 3-second output accurate instead of showing
        stale open trade amount "here and there".
        """
        positions = self._positions(mt5)
        closed_pl = self._closed_pl_today(mt5)
        if closed_pl == 0.0 and closed_pl_fallback is not None:
            closed_pl = float(closed_pl_fallback or 0.0)
        _, _, session_closed_pl = self._risk_session_pl(closed_pl)
        return positions, closed_pl, session_closed_pl, self._account_snapshot(account or {}, positions, closed_pl, session_closed_pl)

    def _refresh_base_account(self, base: Dict[str, Any], mt5: Any, account: Dict[str, Any], closed_pl_fallback: float | None = None) -> Dict[str, Any]:
        positions, closed_pl, session_closed_pl, account_snap = self._fresh_account_state(mt5, account, closed_pl_fallback)
        base["positions"] = positions
        base["open_positions_count"] = len(positions)
        base["account"] = account_snap
        base["session_closed_pl"] = round(session_closed_pl, 2)
        base["floating_pl"] = account_snap.get("floating_pl", 0.0)
        base["combined_session_pl"] = account_snap.get("combined_session_pl", 0.0)
        return base


    # Public API
    def connect_only(self) -> Dict[str, Any]:
        ok, message, account, mt5 = self._connect()
        if not ok:
            return {"ok": False, "phase": "connect", "event": "Connection Failed", "message": message, "thinking": message, "mode": self.rules.get("mode", "Demo"), "symbol": self.symbol}
        positions = self._positions(mt5) if mt5 is not None else []
        closed_pl = self._closed_pl_today(mt5) if mt5 is not None else 0.0
        _, _, session_closed = self._risk_session_pl(closed_pl)
        return {"ok": True, "phase": "connect", "event": "Connected", "message": message, "thinking": message, "mode": self.rules.get("mode", "Demo"), "symbol": self.symbol, "user_key": self.user_key, "user_id": self.user_id, "output_scope": self.output_scope, "account": self._account_snapshot(account or {}, positions, closed_pl, session_closed), "open_positions_count": len(positions), "positions": positions}

    def disconnect_only(self) -> Dict[str, Any]:
        self.disconnect()
        return {"ok": True, "phase": "disconnect", "event": "Disconnected", "message": "MT5 connection closed. You can now switch Demo/Live safely.", "thinking": "Disconnected from MT5.", "mode": self.rules.get("mode", "Demo"), "symbol": self.symbol, "agent_off": True, "decision": {"action": "OFF", "reason": "Disconnected."}}

    def run_cycle(self, execution_enabled: bool = True) -> Dict[str, Any]:
        ok, message, account, mt5 = self._connect()
        mode = self.rules.get("mode", self.profile.get("mode", "Demo"))
        if not ok or mt5 is None:
            return {"ok": False, "phase": "connect", "event": "Connection Failed", "message": message, "thinking": message, "mode": mode, "symbol": self.symbol, "user_key": self.user_key, "user_id": self.user_id, "output_scope": self.output_scope, "decision": {"action": "NONE", "reason": message}}
        rates = self._rates_multi(mt5)
        positions = self._positions(mt5)
        closed_pl = self._closed_pl_today(mt5)
        risk_session_id, risk_baseline_closed_pl, session_closed_pl = self._risk_session_pl(closed_pl)
        account_snap = self._account_snapshot(account or {}, positions, closed_pl, session_closed_pl)
        floating = float(account_snap.get("floating_pl", 0) or 0)
        combined_session_pl = session_closed_pl + floating
        max_loss = abs(float(self.rules.get("max_daily_loss_amount") or self.rules.get("max_daily_loss") or 0))
        market_open, market_reason, market_time_et = self._market_status()
        base = {"ok": True, "phase": "scan", "event": "TradeSmart Agent Scan", "mode": mode, "symbol": self.symbol, "account": account_snap, "positions": positions, "open_positions_count": len(positions), "risk_session_id": risk_session_id, "risk_baseline_closed_pl": risk_baseline_closed_pl, "market_open": market_open, "market_reason": market_reason, "market_time_et": market_time_et, "last_closed_m1": (rates.get("M1", [])[-2] if len(rates.get("M1", [])) >= 2 else {}), "user_key": self.user_key, "user_id": self.user_id, "output_scope": self.output_scope}
        if max_loss > 0 and combined_session_pl <= -max_loss:
            close_results = self._close_all(mt5, positions, reason="TradeSmart max loss") if positions else []
            try:
                time.sleep(0.25)
            except Exception:
                pass
            self._refresh_base_account(base, mt5, account or {}, closed_pl)
            base.update({
                "event": "Risk Stop",
                "message": f"Max daily loss reached this session: floating + session closed P/L {combined_session_pl:.2f} <= -{max_loss:.2f}. Agent must stay OFF until manually toggled on.",
                "thinking": "Risk stop hit for the current toggle-on session. Closing TradeSmart positions and stopping new entries.",
                "decision": {"action": "CLOSE", "reason": "Max daily loss reached for current risk session."},
                "close_results": close_results,
                "max_daily_loss_reached": True,
                "agent_off": True,
            })
            return base
        context = self._strategy_context(rates, positions, account_snap)
        decision, strategy_info = self._choose_signal(context)
        action = str(decision.get("action") or "SCAN").upper()
        base.update({"decision": decision, "strategy": strategy_info.get("winner"), "strategy_info": strategy_info, "thinking": decision.get("reason"), "message": decision.get("reason")})
        if not execution_enabled:
            base["event"] = "Live Strategy Scan"
            return base
        if not market_open:
            base["event"] = "Market Closed"
            base["phase"] = "market_closed"
            base["message"] = market_reason
            base["thinking"] = "Execution blocked: " + market_reason
            base["decision"] = {**decision, "action": "OFF", "reason": market_reason}
            base["agent_off"] = True
            return base
        # Strategy close action is executed by the agent, but the decision came from strategy/risk inputs.
        if action == "CLOSE":
            ticket = decision.get("close_ticket")
            targets = [p for p in positions if not ticket or str(p.get("ticket")) == str(ticket)]
            base["close_results"] = self._close_all(mt5, targets, reason="TradeSmart strategy close")
            try:
                time.sleep(0.20)
            except Exception:
                pass
            self._refresh_base_account(base, mt5, account or {}, closed_pl)
            base["event"] = "Trade Close"
            return base
        if action in ("BUY", "SELL"):
            if len(positions) >= self._max_open():
                base["event"] = "Risk Gate"
                base["message"] = f"Max open trades reached ({len(positions)}/{self._max_open()}). Strategy signal blocked."
                base["thinking"] = base["message"]
                return base
            if not self._dedup_ok(decision):
                base["event"] = "Duplicate Candle Block"
                base["message"] = "Signal already executed on this trigger candle. Waiting for the next closed candle."
                base["thinking"] = base["message"]
                return base
            order = self._send_order(mt5, decision)
            base["order_result"] = order
            base["order_sent"] = bool(order.get("ok"))
            base["event"] = "Order Sent" if order.get("ok") else "Order Rejected"
            if order.get("ok"):
                self._mark_entry(decision)
                try:
                    time.sleep(0.20)
                except Exception:
                    pass
            self._refresh_base_account(base, mt5, account or {}, closed_pl)
        return base

    def snapshot_only(self) -> Dict[str, Any]:
        return self.run_cycle(execution_enabled=False)
