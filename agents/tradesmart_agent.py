"""
tradesmart_agent.py  —  TradeSmart Execution Controller  v4.0
==============================================================
KEY FIXES IN v4
---------------
  1. CANDLE-TIME DEDUP — last_entry_candle_time is now stamped from
     signal.entry_candle_time (the trigger candle), not from last_closed_m1.
     Previously the agent stamped the candle BEFORE the strategy cycle ran,
     then immediately blocked the next cycle's BUY/SELL because it saw the
     same candle time.

  2. HOLD WITH NO OPEN TRADE — when strategy returns HOLD and there are
     no open positions, the agent now shows "Scanning" (not "Tracking")
     and continues without blocking future entries.

  3. SL/TP ALWAYS FORWARDED — signal.sl and signal.tp are read from the
     strategy signal dict and wired directly into the MT5 order request.

  4. DRAW COMMANDS — called every cycle regardless of action.

  5. strategy_common is PRIMARY — external strategies/core is fallback only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

os.environ.setdefault(
    "TRADESMART_MT5_BRIDGE_FILE",
    r"C:\Users\Eric\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\TradeSmart_AI_DrawCommands.json1",
)

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SYMBOL = "XAUUSD"
MAGIC  = 777001


# ══════════════════════════════════════════════
#  SIGNAL DATACLASS
# ══════════════════════════════════════════════

@dataclass
class TradeSignal:
    action:            str            = "NONE"
    symbol:            str            = SYMBOL
    volume:            float          = 0.01
    reason:            str            = "No signal."
    close_ticket:      Optional[int]  = None
    sl:                Optional[float]= None
    tp:                Optional[float]= None
    entry_candle_time: Optional[int]  = None   # time of trigger candle for dedup


# ══════════════════════════════════════════════
#  STRATEGY LOADER
# ══════════════════════════════════════════════

def _load_strategy_common(agent_file: Path):
    candidates = [
        agent_file.parent / "strategy_common.py",
        agent_file.parent.parent / "strategies" / "strategy_common.py",
        agent_file.parent.parent / "strategy_common.py",
    ]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location("tradesmart_strategy_common", str(path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


# ══════════════════════════════════════════════
#  AGENT
# ══════════════════════════════════════════════

class TradeSmartAgent:
    """
    TradeSmart execution agent — controller of last resort.
    strategy_common provides the signal; the agent executes it.
    """

    def __init__(self, profile: Dict[str, Any], rules: Dict[str, Any]):
        self.profile      = profile or {}
        self.rules        = rules   or {}
        self.symbol       = SYMBOL
        self.project_root = Path(__file__).resolve().parents[1]
        self.data_dir     = self.project_root / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.state_file   = self.data_dir / "tradesmart_agent_state.json"
        self._strat_mod   = _load_strategy_common(Path(__file__).resolve())
        self._strat_error: Optional[str] = None if self._strat_mod else "strategy_common.py not found."

    # ──────────────────────────────────────────
    #  MT5
    # ──────────────────────────────────────────

    def _mt5(self):
        try:
            import platform
            if platform.system() != "Windows":
                return None, "MetaTrader5 direct mode only available on Windows."
            import MetaTrader5 as mt5
            return mt5, None
        except Exception as exc:
            return None, f"MetaTrader5 not available: {exc}"

    def _connect(self) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        profile = dict(self.profile or {})
        profile["mode"]   = str(self.rules.get("mode") or profile.get("mode") or "Demo").title()
        profile["symbol"] = self.symbol

        try:
            from frontend.mt5_secure_store import connect_mt5
            ok, message, account = connect_mt5(profile)
            if not ok:
                return False, message, None
            return True, message, account
        except Exception:
            pass

        mt5, error = self._mt5()
        if error:
            return False, error, None

        login         = profile.get("login")
        password      = profile.get("password")
        server        = profile.get("server")
        terminal_path = profile.get("terminal_path") or profile.get("path") or None
        timeout       = min(int(profile.get("timeout", 12000) or 12000), 15000)
        portable      = bool(profile.get("portable", False))

        if not login or not password or not server:
            return False, "Missing MT5 login, password, or server.", None

        try:
            mt5.shutdown()
        except Exception:
            pass

        try:
            init_kwargs = {"timeout": timeout, "portable": portable}
            ok = (mt5.initialize(path=str(terminal_path), **init_kwargs)
                  if terminal_path else mt5.initialize(**init_kwargs))
        except Exception as exc:
            return False, f"MT5 initialize error: {exc}", None

        if not ok:
            return False, f"MT5 init failed: {mt5.last_error()}", None

        try:
            login_ok = mt5.login(int(str(login).strip()), password=str(password),
                                 server=str(server).strip(), timeout=timeout)
        except Exception as exc:
            login_ok = False
            last_err = f"MT5 login exception: {exc}"
        else:
            last_err = mt5.last_error()

        account = mt5.account_info()
        if not login_ok:
            if account is not None:
                data = account._asdict()
                if str(data.get("login", "")).strip() == str(login).strip():
                    return True, f"MT5 connected to {login}.", data
            mt5.shutdown()
            return False, f"MT5 login failed for {login}: {last_err}", None

        if account is None:
            mt5.shutdown()
            return False, f"MT5 account_info failed: {mt5.last_error()}", None

        data = account._asdict()
        if str(data.get("login", "")).strip() != str(login).strip():
            mt5.shutdown()
            return False, f"Wrong account. Expected {login}, got {data.get('login')}.", None

        return True, "Connected to MT5 successfully.", data

    def disconnect(self) -> None:
        mt5, error = self._mt5()
        if not error:
            try:
                mt5.shutdown()
            except Exception:
                pass

    # ──────────────────────────────────────────
    #  PUBLIC SNAPSHOTS
    # ──────────────────────────────────────────

    def connect_only(self) -> Dict[str, Any]:
        ok, message, account = self._connect()
        if not ok:
            return {"ok": False, "phase": "connect", "event": "Connection Failed",
                    "message": message, "thinking": message}
        mt5, _ = self._mt5()
        positions = self._positions(mt5)
        snapshot  = self._account_snapshot(account or {}, positions)
        self.disconnect()
        return {"ok": True, "phase": "connect", "event": "Connected",
                "message": message, "thinking": message,
                "account": snapshot, "open_positions_count": len(positions),
                "positions": positions}

    def snapshot_only(self) -> Dict[str, Any]:
        ok, message, account = self._connect()
        if not ok:
            return {"ok": False, "phase": "snapshot", "event": "Snapshot Failed",
                    "message": message, "thinking": message,
                    "account": {}, "positions": [], "open_positions_count": 0}
        mt5, _ = self._mt5()
        try:
            positions = self._positions(mt5)
            m1        = self._rates_tf(mt5, mt5.TIMEFRAME_M1, 120)
            snapshot  = self._account_snapshot(account or {}, positions)
            return {"ok": True, "phase": "snapshot", "event": "Live Snapshot",
                    "message": "Refreshed.", "thinking": "Snapshot only.",
                    "account": snapshot, "positions": positions,
                    "position_summary": self._position_summary(positions, m1),
                    "open_positions_count": len(positions),
                    "symbol": self.symbol,
                    "mode": self.rules.get("mode", self.profile.get("mode", "Demo")),
                    "execution_enabled": False, "order_sent": False, "order_result": None}
        finally:
            self.disconnect()

    # ──────────────────────────────────────────
    #  DATA CONVERSION
    # ──────────────────────────────────────────

    def _native(self, value: Any) -> Any:
        try:
            if hasattr(value, "item"):
                return value.item()
        except Exception:
            pass
        return round(value, 6) if isinstance(value, float) else value

    def _row_to_dict(self, row: Any, parent: Any = None) -> Dict[str, Any]:
        if hasattr(row, "_asdict"):
            return {str(k): self._native(v) for k, v in row._asdict().items()}
        if isinstance(row, dict):
            return {str(k): self._native(v) for k, v in row.items()}
        names = getattr(getattr(row, "dtype", None), "names", None)
        if names:
            return {str(n): self._native(row[n]) for n in names}
        pnames = getattr(getattr(parent, "dtype", None), "names", None)
        if pnames:
            return {str(n): self._native(row[n]) for n in pnames}
        return {}

    def _rates_tf(self, mt5, timeframe, count: int = 200) -> List[Dict[str, Any]]:
        raw = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
        if raw is None:
            return []
        rows = [self._row_to_dict(r, raw) for r in raw]
        rows = [r for r in rows if r]
        rows.sort(key=lambda x: int(x.get("time", 0) or 0))
        return rows

    def _rates_multi(self, mt5) -> Dict[str, List[Dict[str, Any]]]:
        tf_map = {
            "M1":  (getattr(mt5, "TIMEFRAME_M1",  None), 300),
            "M5":  (getattr(mt5, "TIMEFRAME_M5",  None), 200),
            "M15": (getattr(mt5, "TIMEFRAME_M15", None), 100),
            "H1":  (getattr(mt5, "TIMEFRAME_H1",  None),  60),
        }
        out: Dict[str, List[Dict[str, Any]]] = {}
        for tf, (const, count) in tf_map.items():
            if const is not None:
                rows = self._rates_tf(mt5, const, count)
                if rows:
                    out[tf] = rows
        return out

    def _positions(self, mt5) -> List[Dict[str, Any]]:
        raw = mt5.positions_get(symbol=self.symbol)
        if raw is None:
            return []
        out: List[Dict[str, Any]] = []
        for pos in raw:
            data    = self._row_to_dict(pos)
            comment = str(data.get("comment", ""))
            magic   = int(data.get("magic", 0) or 0)
            if magic == MAGIC or "TradeSmart" in comment:
                out.append(data)
        return out

    def _account_snapshot(self, account: Dict[str, Any],
                          positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        balance  = float(account.get("balance", 0) or 0)
        equity   = float(account.get("equity", balance) or balance)
        return {
            "login":          account.get("login"),
            "server":         account.get("server"),
            "balance":        round(balance, 2),
            "equity":         round(equity, 2),
            "currency":       account.get("currency"),
            "leverage":       account.get("leverage"),
            "open_positions": len(positions or []),
            "daily_pl":       round(equity - balance, 2),
        }

    def _position_summary(self, positions: List[Dict[str, Any]],
                          m1: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        last_time = int((m1[-2] if len(m1) >= 2 else {}).get("time", 0) or 0)
        for pos in positions:
            open_time = int(pos.get("time", 0) or 0)
            candles   = len([c for c in m1
                             if open_time < int(c.get("time", 0) or 0) <= last_time])
            pos_type  = int(pos.get("type", 0) or 0)
            summary.append({
                "ticket":            pos.get("ticket"),
                "direction":         "BUY" if pos_type == 0 else "SELL",
                "volume":            pos.get("volume"),
                "profit":            round(float(pos.get("profit", 0) or 0), 2),
                "candles_since_open": candles,
                "open_price":        pos.get("price_open"),
                "sl":                pos.get("sl"),
                "tp":                pos.get("tp"),
            })
        return summary

    # ──────────────────────────────────────────
    #  STATE
    # ──────────────────────────────────────────

    def _state_key(self) -> str:
        login = self.profile.get("login") or "unknown"
        mode  = self.rules.get("mode") or self.profile.get("mode") or "Demo"
        return f"{login}:{mode}:{self.symbol}"

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ──────────────────────────────────────────
    #  INPUTS + EXTERNAL STRATEGIES
    # ──────────────────────────────────────────

    def _load_neutral_inputs(self) -> Dict[str, Any]:
        runtime_rules = {
            "custom_rules":          self.rules.get("ai_instructions", ""),
            "mode":                  self.rules.get("mode", "Demo"),
            "symbol":                self.symbol,
            "trade_volume":          self.rules.get("trade_volume", 0.01),
            "max_open_trades":       self.rules.get("max_open_trades", 1),
            "max_daily_loss_amount": self.rules.get("max_daily_loss_amount", 0),
        }
        path = self.project_root / "agents" / "inputs" / "__init__.py"
        if not path.exists():
            return runtime_rules
        try:
            spec = importlib.util.spec_from_file_location("dropz_tradesmart_inputs", str(path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                loader = getattr(module, "load_tradesmart_inputs", None)
                if callable(loader):
                    data = loader(project_root=self.project_root, runtime_rules=runtime_rules)
                    if isinstance(data, dict):
                        return data
        except Exception as exc:
            runtime_rules["input_loader_error"] = str(exc)
        return runtime_rules

    def _load_enabled_strategies(self) -> List[Any]:
        strategies: List[Any] = []
        core_path = self.project_root / "strategies" / "core" / "__init__.py"
        if not core_path.exists():
            return strategies
        try:
            spec = importlib.util.spec_from_file_location("dropz_local_strategies_core", str(core_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                loader = getattr(module, "load_enabled_strategies", None)
                if callable(loader):
                    result = loader(project_root=self.project_root)
                    if isinstance(result, list):
                        strategies.extend(result)
        except Exception as exc:
            self._strategy_loader_error = str(exc)
        return strategies

    # ──────────────────────────────────────────
    #  STRATEGY SIGNAL
    # ──────────────────────────────────────────

    def _strategy_signal(
        self,
        rates_multi: Dict[str, List[Dict[str, Any]]],
        positions: List[Dict[str, Any]],
        neutral_inputs: Dict[str, Any],
    ) -> Tuple[TradeSignal, Dict[str, Any]]:
        m1  = rates_multi.get("M1",  [])
        m5  = rates_multi.get("M5",  [])
        m15 = rates_multi.get("M15", [])
        h1  = rates_multi.get("H1",  [])

        context: Dict[str, Any] = {
            "symbol":     self.symbol,
            "rates":      m1,
            "rates_m1":   m1,
            "rates_m5":   m5,
            "rates_m15":  m15,
            "rates_h1":   h1,
            "timeframes": {"M1": m1, "M5": m5, "M15": m15, "H1": h1},
            "positions":  positions,
            "rules":      self.rules,
            "inputs":     neutral_inputs,
            "ai_instructions": neutral_inputs.get("custom_rules",
                                                   self.rules.get("ai_instructions", "")),
            "now": datetime.now(timezone.utc).isoformat(),
        }

        thoughts:  List[str] = []
        evaluated: List[str] = []

        # PRIMARY: strategy_common
        if self._strat_mod and hasattr(self._strat_mod, "build_decision"):
            evaluated.append("xauusd_m15_wick_scalp")
            try:
                raw    = self._strat_mod.build_decision(context) or {}
                action = str(raw.get("action", "NONE")).upper()
                reason = str(raw.get("reason") or raw.get("thought") or "No reason returned.")
                thoughts.append(f"xauusd_m15_wick_scalp: {reason}")

                if action in ("BUY", "SELL", "CLOSE", "HOLD", "SCAN"):
                    return TradeSignal(
                        action            = action,
                        symbol            = self.symbol,
                        volume            = float(raw.get("volume",
                                                   self.rules.get("trade_volume", 0.01)) or 0.01),
                        reason            = reason,
                        close_ticket      = raw.get("close_ticket"),
                        sl                = raw.get("sl"),
                        tp                = raw.get("tp"),
                        entry_candle_time = raw.get("entry_candle_time"),
                    ), {
                        "strategy":     "xauusd_m15_wick_scalp",
                        "thoughts":     thoughts,
                        "evaluated":    evaluated,
                        "raw":          raw,
                        "loaded_count": 1,
                        "loader_error": self._strat_error,
                        "_signal_data": raw,
                    }
            except Exception as exc:
                err = f"strategy_common error: {exc}"
                thoughts.append(err)
                self._strat_error = err

        # FALLBACK: external strategies
        loaded = self._load_enabled_strategies()
        for strategy in loaded:
            name = str(getattr(strategy, "name", strategy.__class__.__name__))
            evaluated.append(name)
            try:
                raw = strategy.evaluate(context) or {}
            except Exception as exc:
                thoughts.append(f"{name} error: {exc}")
                continue
            thought = str(raw.get("thought") or raw.get("reason") or f"{name} no thought.")
            thoughts.append(f"{name}: {thought}")
            action = str(raw.get("action", "NONE")).upper()
            if action in ("BUY", "SELL", "CLOSE", "HOLD"):
                return TradeSignal(
                    action       = action,
                    symbol       = self.symbol,
                    volume       = float(raw.get("volume", self.rules.get("trade_volume", 0.01)) or 0.01),
                    reason       = str(raw.get("reason") or thought),
                    close_ticket = raw.get("close_ticket"),
                    sl           = raw.get("sl"),
                    tp           = raw.get("tp"),
                ), {
                    "strategy":     name,
                    "thoughts":     thoughts,
                    "evaluated":    evaluated,
                    "raw":          raw,
                    "loaded_count": len(loaded),
                    "loader_error": getattr(self, "_strategy_loader_error", None),
                    "_signal_data": raw,
                }

        return TradeSignal(action="NONE", symbol=self.symbol,
                           reason="No enabled strategy returned a signal."), {
            "strategy": None, "thoughts": thoughts or ["No strategies loaded."],
            "evaluated": evaluated, "raw": {}, "loaded_count": len(loaded),
            "loader_error": getattr(self, "_strat_error", None), "_signal_data": {},
        }

    # ──────────────────────────────────────────
    #  RISK HELPERS
    # ──────────────────────────────────────────

    def _symbol_ready(self, mt5) -> Tuple[bool, str]:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return False, f"{self.symbol} not in MT5 Market Watch."
        if not bool(getattr(info, "visible", False)) and not mt5.symbol_select(self.symbol, True):
            return False, f"{self.symbol} could not be selected."
        info = mt5.symbol_info(self.symbol)
        if int(getattr(info, "trade_mode", 0) or 0) == 0:
            return False, f"{self.symbol} trading disabled by broker."
        return True, "Symbol ready."

    def _terminal_trade_allowed(self, mt5) -> Tuple[bool, str]:
        terminal = mt5.terminal_info()
        account  = mt5.account_info()
        if terminal is not None and not bool(getattr(terminal, "trade_allowed", True)):
            return False, "Algo Trading disabled. Enable AutoTrading in MT5."
        if account is not None and not bool(getattr(account, "trade_allowed", True)):
            return False, "Trading disabled for this account."
        return True, "Trading allowed."

    def _normalize_volume(self, mt5, volume: float) -> float:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return round(float(volume), 2)
        min_vol = float(getattr(info, "volume_min",  0.01) or 0.01)
        max_vol = float(getattr(info, "volume_max",  volume) or volume)
        step    = float(getattr(info, "volume_step", 0.01) or 0.01)
        volume  = max(min_vol, min(float(volume), max_vol))
        return round(round(volume / step) * step, 2)

    def _max_loss_hit(self, snapshot: Dict[str, Any], positions: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, float, str]:
        """
        Hard risk stop for TradeSmart tracked positions.

        The old check only compared balance vs equity. That can miss edge cases
        where MT5/account data is delayed or where one tracked position is already
        beyond the loss limit while the combined equity field has not refreshed yet.

        This checks all three live-loss views and trips if ANY reaches the limit:
          1. balance - equity           -> whole account floating drawdown
          2. sum of negative positions  -> all tracked TradeSmart trades combined
          3. worst negative position    -> one tracked trade by itself
        """
        max_loss = float(self.rules.get("max_daily_loss_amount", 0) or 0)
        if max_loss <= 0:
            return False, 0.0, "disabled"

        positions = positions or []
        balance = float(snapshot.get("balance", 0) or 0)
        equity  = float(snapshot.get("equity", balance) or balance)

        equity_loss = max(0.0, balance - equity)
        position_losses = [
            max(0.0, -float(pos.get("profit", 0) or 0))
            for pos in positions
        ]
        combined_position_loss = sum(position_losses)
        worst_position_loss = max(position_losses) if position_losses else 0.0

        loss_views = {
            "account equity drawdown": equity_loss,
            "combined tracked trade loss": combined_position_loss,
            "single tracked trade loss": worst_position_loss,
        }
        reason, live_loss = max(loss_views.items(), key=lambda item: item[1])
        live_loss = round(float(live_loss), 2)
        return live_loss >= max_loss, live_loss, reason

    def _mark_entry_attempt(self, account_state: Dict[str, Any],
                             signal: TradeSignal) -> None:
        now = datetime.now(timezone.utc)
        account_state["last_entry_attempt_epoch"]  = now.timestamp()
        account_state["last_entry_attempt_time"]   = now.isoformat()
        account_state["last_entry_attempt_action"] = signal.action

    # ──────────────────────────────────────────
    #  ORDER SEND
    # ──────────────────────────────────────────

    def _send_order(self, mt5, signal: TradeSignal) -> Dict[str, Any]:
        allowed, msg = self._terminal_trade_allowed(mt5)
        if not allowed:
            return {"ok": False, "message": msg, "retcode": None}

        ready, rmsg = self._symbol_ready(mt5)
        if not ready:
            return {"ok": False, "message": rmsg, "retcode": None}

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "message": f"No live tick for {self.symbol}.", "retcode": None}

        direction  = signal.action.upper()
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        price      = float(tick.ask if direction == "BUY" else tick.bid)
        volume     = self._normalize_volume(mt5, signal.volume)

        sym_info = mt5.symbol_info(self.symbol)
        digits   = int(getattr(sym_info, "digits", 2) or 2) if sym_info else 2

        request: Dict[str, Any] = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       self.symbol,
            "volume":       volume,
            "type":         order_type,
            "price":        price,
            "deviation":    int(self.rules.get("deviation", 30) or 30),
            "magic":        MAGIC,
            "comment":      "TradeSmart Agent",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if signal.sl is not None and float(signal.sl) > 0:
            request["sl"] = round(float(signal.sl), digits)
        if signal.tp is not None and float(signal.tp) > 0:
            request["tp"] = round(float(signal.tp), digits)

        result = mt5.order_send(request)
        if result is None:
            return {"ok": False,
                    "message": f"order_send returned None: {mt5.last_error()}",
                    "request": request}

        data    = result._asdict() if hasattr(result, "_asdict") else dict(result)
        retcode = int(data.get("retcode", 0) or 0)
        success = {int(getattr(mt5, "TRADE_RETCODE_DONE",   10009)),
                   int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
        ok = retcode in success

        if retcode == 10017:
            message = "Trade failed: Algo Trading disabled."
        elif ok:
            sl_txt = f"  SL {signal.sl:.2f}" if signal.sl else ""
            tp_txt = f"  TP {signal.tp:.2f}" if signal.tp else ""
            message = f"{direction} {self.symbol} placed.{sl_txt}{tp_txt}"
        else:
            message = f"Trade failed. Retcode: {retcode}"

        return {"ok": ok, "message": message, "retcode": retcode,
                "request": request, "result": data}

    # ──────────────────────────────────────────
    #  CLOSE POSITION
    # ──────────────────────────────────────────

    def _close_position(self, mt5, ticket: Any) -> Dict[str, Any]:
        target = next((p for p in self._positions(mt5)
                       if str(p.get("ticket")) == str(ticket)), None)
        if target is None:
            return {"ok": False, "message": f"Position {ticket} not found.", "retcode": None}

        allowed, msg = self._terminal_trade_allowed(mt5)
        if not allowed:
            return {"ok": False, "message": msg, "retcode": None}

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "message": f"No live tick.", "retcode": None}

        pos_type   = int(target.get("type", 0) or 0)
        close_type = (mt5.ORDER_TYPE_SELL
                      if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY)
        price      = float(tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask)

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "position":     int(target.get("ticket")),
            "symbol":       self.symbol,
            "volume":       float(target.get("volume", 0.01) or 0.01),
            "type":         close_type,
            "price":        price,
            "deviation":    int(self.rules.get("deviation", 30) or 30),
            "magic":        MAGIC,
            "comment":      "TradeSmart Agent Close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result  = mt5.order_send(request)
        if result is None:
            return {"ok": False,
                    "message": f"close order_send None: {mt5.last_error()}",
                    "request": request}

        data    = result._asdict() if hasattr(result, "_asdict") else dict(result)
        retcode = int(data.get("retcode", 0) or 0)
        success = {int(getattr(mt5, "TRADE_RETCODE_DONE",   10009)),
                   int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
        ok = retcode in success
        return {"ok": ok,
                "message": "Closed." if ok else f"Close failed. Retcode: {retcode}",
                "retcode": retcode, "request": request, "result": data}

    # ──────────────────────────────────────────
    #  DRAW + DEBUG HELPERS
    # ──────────────────────────────────────────

    def _write_draws(self, ctx: Dict[str, Any],
                     decision: Optional[Dict[str, Any]]) -> int:
        if self._strat_mod and hasattr(self._strat_mod, "write_draws"):
            try:
                return self._strat_mod.write_draws(ctx, decision)
            except Exception:
                pass
        return 0

    def _write_debug(self, ctx: Dict[str, Any],
                     result: Dict[str, Any], cmd_count: int) -> None:
        if self._strat_mod and hasattr(self._strat_mod, "write_debug"):
            try:
                self._strat_mod.write_debug(ctx, result, cmd_count)
            except Exception:
                pass

    # ──────────────────────────────────────────
    #  MAIN CYCLE
    # ──────────────────────────────────────────

    def run_cycle(self, execution_enabled: bool = False) -> Dict[str, Any]:
        ok, message, account = self._connect()
        if not ok:
            return {"ok": False, "phase": "connect", "event": "Connection Failed",
                    "message": message, "thinking": message}

        mt5, _ = self._mt5()

        try:
            ready, ready_msg = self._symbol_ready(mt5)
            positions        = self._positions(mt5)
            snapshot         = self._account_snapshot(account or {}, positions)
            rates_multi      = self._rates_multi(mt5)
            m1               = rates_multi.get("M1", [])
            last_closed_m1   = m1[-2] if len(m1) >= 2 else {}
            neutral_inputs   = self._load_neutral_inputs()

            ctx: Dict[str, Any] = {
                "symbol":     self.symbol,
                "rates":      m1,
                "rates_m1":   m1,
                "rates_m5":   rates_multi.get("M5",  []),
                "rates_m15":  rates_multi.get("M15", []),
                "rates_h1":   rates_multi.get("H1",  []),
                "timeframes": rates_multi,
                "positions":  positions,
                "rules":      self.rules,
                "inputs":     neutral_inputs,
                "ai_instructions": neutral_inputs.get("custom_rules",
                                                       self.rules.get("ai_instructions", "")),
                "now": datetime.now(timezone.utc).isoformat(),
            }

            result: Dict[str, Any] = {
                "ok":                   True,
                "phase":                "scan",
                "event":                "Strategy Scan",
                "message":              "TradeSmart scanned XAUUSD.",
                "thinking":             "Reading M1/M5/M15/H1, account, positions, strategy.",
                "symbol":               self.symbol,
                "mode":                 self.rules.get("mode", self.profile.get("mode", "Demo")),
                "account":              snapshot,
                "last_closed_m1":       last_closed_m1,
                "open_positions_count": len(positions),
                "positions":            positions,
                "position_summary":     self._position_summary(positions, m1),
                "decision":             {"action": "NONE", "symbol": self.symbol,
                                         "reason": "No decision yet."},
                "strategy":             None,
                "strategy_info":        {},
                "inputs":               neutral_inputs,
                "execution_enabled":    execution_enabled,
                "order_sent":           False,
                "order_result":         None,
                "risk_blocks":          [],
                "max_daily_loss_reached": False,
            }

            if not ready:
                result.update({"event": "Symbol Blocked",
                                "message": ready_msg, "thinking": ready_msg})
                self._write_draws(ctx, None)
                return result

            # Max daily loss / hard kill-switch
            max_loss_hit, live_loss, loss_reason = self._max_loss_hit(snapshot, positions)
            if max_loss_hit:
                result.update({
                    "max_daily_loss_reached": True,
                    "risk_lock_reason": loss_reason,
                    "event":   "Max Loss Reached",
                    "message": f"Max loss limit reached by {loss_reason}: ${live_loss}. Agent stopped and tracked trades are being closed.",
                    "thinking": f"Risk lock: {loss_reason} ${live_loss}. No new trades until the agent is manually turned back on.",
                })
                result["risk_blocks"].append(f"Max Loss ({loss_reason}): ${live_loss}")
                closes = []
                if execution_enabled and positions:
                    for pos in positions:
                        ticket = pos.get("ticket")
                        if ticket not in (None, ""):
                            closes.append(self._close_position(mt5, ticket))
                result["order_result"] = closes
                result["order_sent"]   = any(isinstance(c, dict) and c.get("ok") for c in closes)
                result["closed_for_risk"] = closes
                self._write_draws(ctx, result)
                return result

            # Get signal
            signal, info = self._strategy_signal(rates_multi, positions, neutral_inputs)
            result["decision"]      = asdict(signal)
            result["strategy"]      = info.get("strategy")
            result["strategy_info"] = info
            thoughts = info.get("thoughts") or []
            result["thinking"] = " | ".join(thoughts[-4:]) or signal.reason
            result["message"]  = signal.reason or result["message"]

            if info.get("loader_error"):
                result["strategy_loader_note"] = info.get("loader_error")

            # Build draw payload
            raw_decision = dict(info.get("_signal_data") or {})
            raw_decision.update({"action": signal.action, "reason": signal.reason,
                                  "sl": signal.sl, "tp": signal.tp})

            # Write draws every cycle
            cmd_count = self._write_draws(ctx, raw_decision)
            self._write_debug(ctx, raw_decision, cmd_count)
            result["draw_command_count"] = cmd_count

            state         = self._load_state()
            key           = self._state_key()
            account_state = state.setdefault(key, {})

            # ── SCAN — just display status ─────────
            if signal.action == "SCAN":
                result["event"]   = "Scanning"
                result["message"] = signal.reason
                return result

            # ── HOLD ──────────────────────────────
            if signal.action == "HOLD":
                result["event"]   = "Tracking" if positions else "Scanning"
                result["message"] = signal.reason
                return result

            # ── CLOSE ─────────────────────────────
            if signal.action == "CLOSE" and signal.close_ticket:
                result["event"] = "Exit Signal"
                if execution_enabled:
                    cr = self._close_position(mt5, signal.close_ticket)
                    result.update({"order_result": cr, "order_sent": bool(cr.get("ok")),
                                   "message": cr.get("message", signal.reason)})
                    if cr.get("ok"):
                        account_state["last_exit_time"]   = datetime.now(timezone.utc).isoformat()
                        account_state["last_exit_ticket"] = signal.close_ticket
                        self._save_state(state)
                return result

            # ── BUY / SELL ────────────────────────
            if signal.action not in ("BUY", "SELL"):
                result["event"] = "Strategy Scan"
                return result

            # Max open trades
            max_open = int(self.rules.get("max_open_trades", 1) or 1)
            if len(positions) >= max_open:
                result.update({"event": "Risk Blocked",
                                "message": f"Max open trades {len(positions)}/{max_open}.",
                                "thinking": "Waiting for open trade to close."})
                return result

            # ── DEDUP: use entry_candle_time from strategy signal ──
            # This is the TIME of the actual trigger candle, NOT the last closed M1.
            # Prevents the same candle firing twice while allowing the very next
            # different candle to fire immediately.
            trigger_ct    = int(signal.entry_candle_time or 0)
            last_entry_ct = int(account_state.get("last_entry_candle_time", 0) or 0)

            if trigger_ct and trigger_ct == last_entry_ct:
                result.update({"event": "Tracking",
                                "message": "Trigger candle already processed — waiting for next setup.",
                                "thinking": "Dedup: same trigger candle time seen before."})
                return result

            if not execution_enabled:
                result.update({"event": "Preview",
                                "message": f"{signal.action} setup — execution is off."})
                return result

            # Fire the order
            self._mark_entry_attempt(account_state, signal)
            self._save_state(state)

            order_result = self._send_order(mt5, signal)
            result.update({
                "event":        "Order Sent" if order_result.get("ok") else "Order Failed",
                "order_sent":   bool(order_result.get("ok")),
                "order_result": order_result,
                "message":      order_result.get("message", signal.reason),
            })

            if order_result.get("ok"):
                now_dt = datetime.now(timezone.utc)
                # Stamp trigger candle time — prevents same setup firing twice
                if trigger_ct:
                    account_state["last_entry_candle_time"] = trigger_ct
                account_state["last_entry_action"] = signal.action
                account_state["last_entry_time"]   = now_dt.isoformat()
                account_state["last_entry_epoch"]  = now_dt.timestamp()
                account_state["last_entry_sl"]     = signal.sl
                account_state["last_entry_tp"]     = signal.tp
                self._save_state(state)

            return result

        finally:
            self.disconnect()
