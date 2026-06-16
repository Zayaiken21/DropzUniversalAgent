from __future__ import annotations

import importlib.util
import json
import time
import os
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
            # Clear any previous lock — user manually toggled ON to start fresh
            bucket.pop("risk_locked", None)
            bucket.pop("risk_lock_reason", None)
            bucket.pop("risk_locked_at", None)
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

    def _state_lock_path(self) -> Path:
        return self.state_file.with_suffix(".lock")

    def _acquire_state_lock(self, timeout: float = 2.0):
        """Small file lock for localhost/127.0.0.1 Streamlit reruns/tabs.

        Streamlit can rerun the same page quickly. This lock makes the entry
        cooldown reservation atomic so two refreshes cannot place two trades
        before the JSON state file updates.
        """
        lock_path = self._state_lock_path()
        start = time.time()
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                return fd
            except FileExistsError:
                try:
                    # Clear stale locks left behind by a killed local process.
                    if time.time() - lock_path.stat().st_mtime > 8:
                        lock_path.unlink(missing_ok=True)
                        continue
                except Exception:
                    pass
                if time.time() - start >= timeout:
                    return None
                time.sleep(0.03)
            except Exception:
                return None

    def _release_state_lock(self, fd: Any) -> None:
        try:
            if fd is not None:
                os.close(fd)
        except Exception:
            pass
        try:
            self._state_lock_path().unlink(missing_ok=True)
        except Exception:
            pass

    def _open_ticket_set(self, positions: List[Dict[str, Any]]) -> set[str]:
        tickets: set[str] = set()
        for pos in positions or []:
            if not isinstance(pos, dict):
                continue
            ticket = pos.get("ticket") or pos.get("position") or pos.get("order")
            if ticket not in (None, ""):
                tickets.add(str(ticket))
        return tickets

    def _mark_trade_closed_cooldown(self, reason: str = "trade closed") -> None:
        """Start the same cooldown after a close/SL/TP as after an entry."""
        fd = self._acquire_state_lock()
        try:
            state = self._load_state()
            key = self._state_key()
            bucket = state.setdefault(key, {})
            now = time.time()
            bucket["last_trade_close_ts"] = now
            bucket["last_trade_close_reason"] = reason
            bucket["last_order_cooldown_seconds"] = self._trade_cooldown_seconds()
            bucket["updated"] = now
            self._save_state(state)
        finally:
            self._release_state_lock(fd)

    def _track_closed_positions_for_cooldown(self, positions: List[Dict[str, Any]]) -> None:
        """Detect positions that disappeared since the prior cycle.

        This catches TP/SL/manual broker-side closes and starts the 10-second
        cooldown before another entry is allowed.
        """
        current = self._open_ticket_set(positions)
        fd = self._acquire_state_lock()
        try:
            state = self._load_state()
            key = self._state_key()
            bucket = state.setdefault(key, {})
            previous_raw = bucket.get("last_seen_open_tickets")
            previous = set(str(x) for x in previous_raw) if isinstance(previous_raw, list) else None

            if previous is not None:
                removed = previous - current
                if removed:
                    now = time.time()
                    bucket["last_trade_close_ts"] = now
                    bucket["last_trade_close_reason"] = "position closed"
                    bucket["last_closed_ticket_count"] = len(removed)
                    bucket["last_order_cooldown_seconds"] = self._trade_cooldown_seconds()
                    bucket["updated"] = now

            bucket["last_seen_open_tickets"] = sorted(current)
            bucket["updated"] = time.time()
            self._save_state(state)
        finally:
            self._release_state_lock(fd)

    def _trade_cooldown_seconds(self) -> float:
        """Minimum seconds between successfully placed TradeSmart entries.

        Default is 10 seconds. This is intentionally enforced inside the agent,
        not only the Streamlit page, so local, cloud, and future runners all obey
        the same protection.
        """
        try:
            return max(0.0, float(self.rules.get("trade_cooldown_seconds", 10) or 10))
        except Exception:
            return 10.0
    def _entry_execution_blocked(self) -> Tuple[bool, str]:
        """Hard entry gate checked before every order path — multiple layers."""
        # Layer 1: Explicit risk/emergency flags passed from the page
        if bool(self.rules.get("risk_lock_active") or self.rules.get("execution_blocked") or self.rules.get("emergency_stop")):
            return True, "Execution blocked by TradeSmart risk lock / emergency stop."
        # Layer 2: Agent toggled OFF
        if bool(self.rules.get("agent_off") or self.rules.get("manual_stop_requested") or self.rules.get("stop_requested")):
            return True, "Execution blocked because the TradeSmart agent is OFF."
        # Layer 3: Persistent state-level risk lock (survives across cycles)
        state = self._load_state()
        key = self._state_key()
        if bool((state.get(key) or {}).get("risk_locked")):
            return True, "Execution blocked by persistent risk lock in agent state. Toggle OFF and back ON to reset."
        return False, ""

    def _set_risk_lock(self, reason: str) -> None:
        """Persist a risk lock in agent state so no order slips in between cycles."""
        state = self._load_state()
        key = self._state_key()
        bucket = state.setdefault(key, {})
        bucket["risk_locked"] = True
        bucket["risk_lock_reason"] = reason
        bucket["risk_locked_at"] = time.time()
        self._save_state(state)

    def _last_entry_timestamp(self) -> float:
        state = self._load_state()
        key = self._state_key()
        bucket = state.get(key) or {}
        sent_ts = float(bucket.get("last_order_sent_ts") or 0.0)
        attempt_ts = float(bucket.get("last_order_attempt_ts") or 0.0)
        close_ts = float(bucket.get("last_trade_close_ts") or 0.0)
        return max(sent_ts, attempt_ts, close_ts)

    def _reserve_order_attempt(self) -> Tuple[bool, float]:
        """Atomically reserve the 10-second entry window before order_send.

        This prevents localhost/127.0.0.1 Streamlit reruns or multiple browser
        tabs from both passing the cooldown check before the first order result
        is written.
        """
        cooldown = self._trade_cooldown_seconds()
        if cooldown <= 0:
            return True, 0.0

        fd = self._acquire_state_lock()
        if fd is None:
            # Fail closed: if we cannot lock state, do not place a trade.
            return False, cooldown

        try:
            state = self._load_state()
            key = self._state_key()
            bucket = state.setdefault(key, {})
            last_ts = max(
                float(bucket.get("last_order_sent_ts") or 0.0),
                float(bucket.get("last_order_attempt_ts") or 0.0),
                float(bucket.get("last_trade_close_ts") or 0.0),
            )
            remaining = max(0.0, cooldown - (time.time() - last_ts))
            if remaining > 0:
                return False, remaining

            now = time.time()
            bucket["last_order_attempt_ts"] = now
            bucket["last_order_cooldown_seconds"] = cooldown
            bucket["updated"] = now
            self._save_state(state)
            return True, 0.0
        finally:
            self._release_state_lock(fd)


    def _cooldown_remaining(self) -> float:
        cooldown = self._trade_cooldown_seconds()
        if cooldown <= 0:
            return 0.0
        last_ts = self._last_entry_timestamp()
        if last_ts <= 0:
            return 0.0
        return max(0.0, cooldown - (time.time() - last_ts))

    def _mark_order_sent(self) -> None:
        fd = self._acquire_state_lock()
        try:
            state = self._load_state()
            key = self._state_key()
            bucket = state.setdefault(key, {})
            now = time.time()
            bucket["last_order_sent_ts"] = now
            bucket["last_order_attempt_ts"] = now
            bucket["last_order_cooldown_seconds"] = self._trade_cooldown_seconds()
            bucket["updated"] = now
            self._save_state(state)
        finally:
            self._release_state_lock(fd)

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
        blocked, block_reason = self._entry_execution_blocked()
        if blocked:
            return {"ok": False, "message": block_reason, "blocked": True}

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
        # XAUUSD: practical minimum stop distance to avoid broker rejection (retcode 10016).
        # Keep this tight — wider = SL gets hit before TP on 1:1 trades.
        min_stop = max(stops_level, freeze_level, spread * 1.5, point * 30.0, 0.30)

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
            # 1:1 fallback — only override TP when the strategy did not provide a valid one
            if tp_raw <= 0 or tp_raw <= price + min_stop:
                tp_raw = price + risk          # exact 1:1
                adjusted = True
        else:
            if sl_raw <= 0 or sl_raw <= price + min_stop:
                sl_raw = price + min_stop
                adjusted = True
            risk = max(sl_raw - price, min_stop)
            if tp_raw <= 0 or tp_raw >= price - min_stop:
                tp_raw = price - risk          # exact 1:1
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


    def close_all_positions(self, reason: str = "TradeSmart stop") -> Dict[str, Any]:
        """Close TradeSmart positions only. This method never opens a new trade."""
        ok, message, account, mt5 = self._connect()
        mode = self.rules.get("mode", self.profile.get("mode", "Demo"))
        if not ok or mt5 is None:
            return {"ok": False, "phase": "close", "event": "Emergency Close Error", "message": message, "thinking": message, "mode": mode, "symbol": self.symbol, "agent_off": True, "decision": {"action": "OFF", "reason": message}}
        positions = self._positions(mt5)
        close_results = self._close_all(mt5, positions, reason=reason) if positions else []
        if positions:
            self._mark_trade_closed_cooldown("close all positions")
        try:
            time.sleep(0.25)
        except Exception:
            pass
        closed_pl = self._closed_pl_today(mt5)
        _, _, session_closed = self._risk_session_pl(closed_pl)
        fresh_positions = self._positions(mt5)
        account_snap = self._account_snapshot(account or {}, fresh_positions, closed_pl, session_closed)
        return {
            "ok": True,
            "phase": "close",
            "event": "Emergency Close",
            "message": "TradeSmart positions closed or no positions were open. No new orders were allowed.",
            "thinking": reason,
            "mode": mode,
            "symbol": self.symbol,
            "account": account_snap,
            "positions": fresh_positions,
            "open_positions_count": len(fresh_positions),
            "close_results": close_results,
            "agent_off": True,
            "decision": {"action": "OFF", "reason": reason},
        }

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
        self._track_closed_positions_for_cooldown(positions)
        closed_pl = self._closed_pl_today(mt5)
        risk_session_id, risk_baseline_closed_pl, session_closed_pl = self._risk_session_pl(closed_pl)
        account_snap = self._account_snapshot(account or {}, positions, closed_pl, session_closed_pl)
        floating = float(account_snap.get("floating_pl", 0) or 0)
        combined_session_pl = session_closed_pl + floating
        max_loss = abs(float(self.rules.get("max_daily_loss_amount") or self.rules.get("max_daily_loss") or 0))
        market_open, market_reason, market_time_et = self._market_status()
        base = {"ok": True, "phase": "scan", "event": "TradeSmart Agent Scan", "mode": mode, "symbol": self.symbol, "account": account_snap, "positions": positions, "open_positions_count": len(positions), "risk_session_id": risk_session_id, "risk_baseline_closed_pl": risk_baseline_closed_pl, "market_open": market_open, "market_reason": market_reason, "market_time_et": market_time_et, "last_closed_m1": (rates.get("M1", [])[-2] if len(rates.get("M1", [])) >= 2 else {}), "user_key": self.user_key, "user_id": self.user_id, "output_scope": self.output_scope}
        if bool(self.rules.get("risk_lock_active") or self.rules.get("execution_blocked") or self.rules.get("emergency_stop")):
            base.update({
                "event": "Risk Lock",
                "phase": "risk_locked",
                "message": "Execution blocked by TradeSmart risk lock. Clear the lock and manually toggle ON to restart.",
                "thinking": "Risk lock is active. No new orders are allowed.",
                "decision": {"action": "OFF", "reason": "Risk lock active."},
                "agent_off": True,
                "max_daily_loss_reached": True,
            })
            return base
        if max_loss > 0 and combined_session_pl <= -max_loss:
            close_results = self._close_all(mt5, positions, reason="TradeSmart max loss") if positions else []
            try:
                time.sleep(0.25)
            except Exception:
                pass
            # Persist the lock so no race-condition cycle can sneak an order through
            lock_reason = f"Max daily loss reached: session P/L {combined_session_pl:.2f} <= -{max_loss:.2f}."
            self._set_risk_lock(lock_reason)
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
        min_score = float(self.rules.get("min_strategy_score", 0.75) or 0.75)
        score = float(decision.get("score", decision.get("confidence", 0)) or 0)
        if action in ("BUY", "SELL") and score < min_score:
            decision = {
                **decision,
                "action": "SCAN",
                "reason": f"Setup score {score:.2f} is below TradeSmart's fixed 75% execution filter.",
            }
            action = "SCAN"
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
            if targets:
                self._mark_trade_closed_cooldown("strategy close")
            try:
                time.sleep(0.20)
            except Exception:
                pass
            self._refresh_base_account(base, mt5, account or {}, closed_pl)
            base["event"] = "Trade Close"
            return base
        if action in ("BUY", "SELL"):
            blocked, block_reason = self._entry_execution_blocked()
            if blocked:
                base["event"] = "Execution Blocked"
                base["message"] = block_reason
                base["thinking"] = block_reason
                base["decision"] = {**decision, "action": "OFF", "reason": block_reason}
                base["agent_off"] = True
                return base
            if len(positions) >= self._max_open():
                base["event"] = "Risk Gate"
                base["message"] = f"Max open trades reached ({len(positions)}/{self._max_open()}). Strategy signal blocked."
                base["thinking"] = base["message"]
                return base
            cooldown_remaining = self._cooldown_remaining()
            if cooldown_remaining > 0:
                base["event"] = "Trade Cooldown"
                base["message"] = f"Trade cooldown active. Waiting {cooldown_remaining:.1f}s before another entry can be placed."
                base["thinking"] = base["message"]
                base["trade_cooldown_remaining"] = round(cooldown_remaining, 1)
                return base
            if not self._dedup_ok(decision):
                base["event"] = "Duplicate Candle Block"
                base["message"] = "Signal already executed on this trigger candle. Waiting for the next closed candle."
                base["thinking"] = base["message"]
                return base
            reserved, reserved_remaining = self._reserve_order_attempt()
            if not reserved:
                base["event"] = "Trade Cooldown"
                base["message"] = f"Trade cooldown active. Waiting {reserved_remaining:.1f}s before another entry can be placed."
                base["thinking"] = base["message"]
                base["trade_cooldown_remaining"] = round(reserved_remaining, 1)
                return base
            blocked, block_reason = self._entry_execution_blocked()
            if blocked:
                base["event"] = "Execution Blocked"
                base["message"] = block_reason
                base["thinking"] = block_reason
                base["decision"] = {**decision, "action": "OFF", "reason": block_reason}
                base["agent_off"] = True
                return base
            order = self._send_order(mt5, decision)
            base["order_result"] = order
            base["order_sent"] = bool(order.get("ok"))
            base["event"] = "Order Sent" if order.get("ok") else "Order Rejected"
            if order.get("ok"):
                self._mark_entry(decision)
                self._mark_order_sent()
                try:
                    time.sleep(0.20)
                except Exception:
                    pass
            self._refresh_base_account(base, mt5, account or {}, closed_pl)
        return base

    def snapshot_only(self) -> Dict[str, Any]:
        return self.run_cycle(execution_enabled=False)
