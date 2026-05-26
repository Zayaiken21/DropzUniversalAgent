from __future__ import annotations
import os

import os

os.environ["TRADESMART_MT5_BRIDGE_FILE"] = (
    r"C:\Users\Eric\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\TradeSmart_AI_DrawCommands.json1"
)

import importlib.util
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SYMBOL = "XAUUSD"
MAGIC = 777001


@dataclass
class TradeSignal:
    action: str = "NONE"  # NONE, HOLD, BUY, SELL, CLOSE
    symbol: str = SYMBOL
    volume: float = 0.01
    reason: str = "No signal."
    close_ticket: Optional[int] = None


class TradeSmartAgent:
    """
    TradeSmart execution agent.

    The Streamlit page only passes profile + rules. The agent:
      - connects to MT5 locally
      - loads neutral inputs from agents/inputs
      - loads strategies from /strategies
      - decides BUY/SELL/CLOSE/HOLD from strategy output
      - applies risk protections
      - places/closes real MT5 XAUUSD trades
      - returns UI-safe dictionaries for the page/output renderer
    """

    def __init__(self, profile: Dict[str, Any], rules: Dict[str, Any]):
        self.profile = profile or {}
        self.rules = rules or {}
        self.symbol = SYMBOL
        self.project_root = Path(__file__).resolve().parents[1]
        self.data_dir = self.project_root / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / "tradesmart_agent_state.json"

    # ---------- platform ----------
    def _mt5(self):
        try:
            import MetaTrader5 as mt5
            return mt5, None
        except Exception as exc:
            return None, f"MetaTrader5 is not available here: {exc}"

    def _connect(self) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        mt5, error = self._mt5()
        if error:
            return False, error, None

        login = self.profile.get("login")
        password = self.profile.get("password")
        server = self.profile.get("server")
        terminal_path = self.profile.get("terminal_path") or self.profile.get("path") or None
        timeout = int(self.profile.get("timeout", 60000) or 60000)
        portable = bool(self.profile.get("portable", False))

        if not login or not password or not server:
            return False, "Missing MT5 login, password, or server.", None

        try:
            mt5.shutdown()
        except Exception:
            pass

        try:
            kwargs = {
                "login": int(login),
                "password": str(password),
                "server": str(server),
                "timeout": timeout,
                "portable": portable,
            }
            ok = mt5.initialize(path=str(terminal_path), **kwargs) if terminal_path else mt5.initialize(**kwargs)
        except Exception as exc:
            return False, f"MT5 initialize error: {exc}", None

        if not ok:
            return False, f"MT5 initialization failed: {mt5.last_error()}", None

        account = mt5.account_info()
        if account is None:
            msg = f"MT5 account_info failed: {mt5.last_error()}"
            mt5.shutdown()
            return False, msg, None

        return True, "Connected to MT5 successfully.", account._asdict()

    def disconnect(self) -> None:
        mt5, error = self._mt5()
        if not error:
            try:
                mt5.shutdown()
            except Exception:
                pass

    def connect_only(self) -> Dict[str, Any]:
        ok, message, account = self._connect()
        if not ok:
            return {"ok": False, "phase": "connect", "event": "Connection Failed", "message": message, "thinking": message}

        mt5, _ = self._mt5()
        positions = self._positions(mt5)
        snapshot = self._account_snapshot(account or {}, positions)
        self.disconnect()
        return {
            "ok": True,
            "phase": "connect",
            "event": "Connected",
            "message": message,
            "thinking": message,
            "account": snapshot,
            "open_positions_count": len(positions),
            "positions": positions,
        }

    def snapshot_only(self) -> Dict[str, Any]:
        """
        Fresh account/position snapshot for the currently selected MT5 profile.
        This is intentionally execution-free. It prevents the Streamlit page from
        showing stale Demo/Live balances or old open-trade counts after the agent
        is stopped or the user switches modes.
        """
        ok, message, account = self._connect()
        if not ok:
            return {
                "ok": False,
                "phase": "snapshot",
                "event": "Snapshot Failed",
                "message": message,
                "thinking": message,
                "account": {},
                "positions": [],
                "open_positions_count": 0,
            }

        mt5, _ = self._mt5()
        try:
            positions = self._positions(mt5)
            rates = self._rates(mt5, 120)
            snapshot = self._account_snapshot(account or {}, positions)
            return {
                "ok": True,
                "phase": "snapshot",
                "event": "Live Snapshot",
                "message": "Live account and XAUUSD TradeSmart positions refreshed.",
                "thinking": "Refreshing the selected MT5 profile only. No orders are sent during this snapshot.",
                "account": snapshot,
                "positions": positions,
                "position_summary": self._position_summary(positions, rates),
                "open_positions_count": len(positions),
                "symbol": self.symbol,
                "mode": self.rules.get("mode", self.profile.get("mode", "Demo")),
                "execution_enabled": False,
                "order_sent": False,
                "order_result": None,
            }
        finally:
            self.disconnect()

    # ---------- conversion ----------
    def _native(self, value: Any) -> Any:
        try:
            if hasattr(value, "item"):
                return value.item()
        except Exception:
            pass
        if isinstance(value, float):
            return round(value, 6)
        return value

    def _row_to_dict(self, row: Any, parent: Any = None) -> Dict[str, Any]:
        if hasattr(row, "_asdict"):
            return {str(k): self._native(v) for k, v in row._asdict().items()}
        if isinstance(row, dict):
            return {str(k): self._native(v) for k, v in row.items()}
        names = getattr(getattr(row, "dtype", None), "names", None)
        if names:
            return {str(name): self._native(row[name]) for name in names}
        parent_names = getattr(getattr(parent, "dtype", None), "names", None)
        if parent_names:
            return {str(name): self._native(row[name]) for name in parent_names}
        return {}

    def _rates(self, mt5, count: int = 100) -> List[Dict[str, Any]]:
        raw = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, count)
        if raw is None:
            return []
        rows = [self._row_to_dict(row, raw) for row in raw]
        rows = [row for row in rows if row]
        rows.sort(key=lambda item: int(item.get("time", 0) or 0))
        return rows

    def _positions(self, mt5) -> List[Dict[str, Any]]:
        raw = mt5.positions_get(symbol=self.symbol)
        if raw is None:
            return []
        positions: List[Dict[str, Any]] = []
        for pos in raw:
            data = self._row_to_dict(pos)
            comment = str(data.get("comment", ""))
            magic = int(data.get("magic", 0) or 0)
            if magic == MAGIC or "TradeSmart" in comment:
                positions.append(data)
        return positions

    def _account_snapshot(self, account: Dict[str, Any], positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        balance = float(account.get("balance", 0) or 0)
        equity = float(account.get("equity", balance) or balance)
        daily_pl = round(equity - balance, 2)
        return {
            "login": account.get("login"),
            "server": account.get("server"),
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "currency": account.get("currency"),
            "leverage": account.get("leverage"),
            "open_positions": len(positions or []),
            "daily_pl": daily_pl,
        }


    def _position_summary(self, positions: List[Dict[str, Any]], rates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        last_time = int((rates[-2] if len(rates) >= 2 else {}).get("time", 0) or 0)
        for pos in positions:
            open_time = int(pos.get("time", 0) or 0)
            candles = len([
                candle for candle in rates
                if int(candle.get("time", 0) or 0) > open_time
                and int(candle.get("time", 0) or 0) <= last_time
            ])
            pos_type = int(pos.get("type", 0) or 0)
            summary.append({
                "ticket": pos.get("ticket"),
                "direction": "BUY" if pos_type == 0 else "SELL",
                "volume": pos.get("volume"),
                "profit": round(float(pos.get("profit", 0) or 0), 2),
                "candles_since_open": candles,
            })
        return summary

    # ---------- state ----------
    def _state_key(self) -> str:
        login = self.profile.get("login") or "unknown"
        mode = self.rules.get("mode") or self.profile.get("mode") or "Demo"
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

    # ---------- neutral inputs + strategies ----------
    def _load_neutral_inputs(self) -> Dict[str, Any]:
        path = self.project_root / "agents" / "inputs" / "__init__.py"
        runtime_rules = {
            "custom_rules": self.rules.get("ai_instructions", ""),
            "mode": self.rules.get("mode", "Demo"),
            "symbol": self.symbol,
            "trade_volume": self.rules.get("trade_volume", 0.01),
            "max_open_trades": self.rules.get("max_open_trades", 1),
            "max_daily_loss_amount": self.rules.get("max_daily_loss_amount", 0),
        }
        if not path.exists():
            return runtime_rules
        try:
            spec = importlib.util.spec_from_file_location("dropz_tradesmart_inputs", str(path))
            if not spec or not spec.loader:
                return runtime_rules
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
        """
        Neutral local strategy loader.
        It does not import `strategies.core` by package name, so PyPI packages
        named `strategies` cannot shadow your local folder.
        """
        strategies: List[Any] = []
        core_path = self.project_root / "strategies" / "core" / "__init__.py"

        if core_path.exists():
            try:
                spec = importlib.util.spec_from_file_location("dropz_local_strategies_core", str(core_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    loader = getattr(module, "load_enabled_strategies", None)
                    if callable(loader):
                        loaded = loader(project_root=self.project_root)
                        if isinstance(loaded, list):
                            strategies.extend([s for s in loaded if getattr(s, "enabled", True)])
            except Exception as exc:
                self._strategy_loader_error = str(exc)

        return strategies

    def _strategy_signal(self, rates: List[Dict[str, Any]], positions: List[Dict[str, Any]], neutral_inputs: Dict[str, Any]) -> Tuple[TradeSignal, Dict[str, Any]]:
        context = {
            "symbol": self.symbol,
            "rates": rates,
            "positions": positions,
            "rules": self.rules,
            "inputs": neutral_inputs,
            "ai_instructions": neutral_inputs.get("custom_rules", self.rules.get("ai_instructions", "")),
            "now": datetime.now(timezone.utc).isoformat(),
        }

        loaded = self._load_enabled_strategies()
        thoughts: List[str] = []
        evaluated: List[str] = []

        for strategy in loaded:
            name = str(getattr(strategy, "name", strategy.__class__.__name__))
            evaluated.append(name)
            try:
                raw = strategy.evaluate(context) or {}
            except Exception as exc:
                thoughts.append(f"{name} error: {exc}")
                continue

            thought = str(raw.get("thought") or raw.get("reason") or f"{name} returned no thought.")
            thoughts.append(f"{name}: {thought}")
            action = str(raw.get("action", "NONE")).upper()

            if action in {"BUY", "SELL", "CLOSE", "HOLD"}:
                return TradeSignal(
                    action=action,
                    symbol=self.symbol,
                    volume=float(raw.get("volume", self.rules.get("trade_volume", 0.01)) or 0.01),
                    reason=str(raw.get("reason") or thought),
                    close_ticket=raw.get("close_ticket"),
                ), {
                    "strategy": name,
                    "thoughts": thoughts,
                    "evaluated": evaluated,
                    "raw": raw,
                    "loaded_count": len(loaded),
                    "loader_error": getattr(self, "_strategy_loader_error", None),
                }

        return TradeSignal(action="NONE", symbol=self.symbol, reason="No enabled strategy returned a signal."), {
            "strategy": None,
            "thoughts": thoughts or ["No enabled strategy returned a signal. Add or enable a strategy file inside the local strategies folder."],
            "evaluated": evaluated,
            "raw": {},
            "loaded_count": len(loaded),
            "loader_error": getattr(self, "_strategy_loader_error", None),
        }

    # ---------- risk + execution ----------
    def _symbol_ready(self, mt5) -> Tuple[bool, str]:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return False, f"{self.symbol} was not found in MT5 Market Watch."
        if not bool(getattr(info, "visible", False)) and not mt5.symbol_select(self.symbol, True):
            return False, f"{self.symbol} could not be selected in MT5 Market Watch."
        info = mt5.symbol_info(self.symbol)
        trade_mode = int(getattr(info, "trade_mode", 0) or 0) if info is not None else 0
        if trade_mode == 0:
            return False, f"{self.symbol} trading is disabled by this broker/account."
        return True, "Symbol ready."

    def _terminal_trade_allowed(self, mt5) -> Tuple[bool, str]:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is not None and not bool(getattr(terminal, "trade_allowed", True)):
            return False, "MT5 Algo Trading is disabled in the terminal. Turn on Algo Trading/AutoTrading."
        if account is not None and not bool(getattr(account, "trade_allowed", True)):
            return False, "Trading is disabled for this MT5 account. Use the main trading password, not investor/read-only mode."
        return True, "Trading allowed."

    def _normalize_volume(self, mt5, volume: float) -> float:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return round(float(volume), 2)
        min_vol = float(getattr(info, "volume_min", 0.01) or 0.01)
        max_vol = float(getattr(info, "volume_max", volume) or volume)
        step = float(getattr(info, "volume_step", 0.01) or 0.01)
        volume = max(min_vol, min(float(volume), max_vol))
        steps = round(volume / step)
        return round(steps * step, 2)

    def _send_order(self, mt5, signal: TradeSignal) -> Dict[str, Any]:
        allowed, msg = self._terminal_trade_allowed(mt5)
        if not allowed:
            return {"ok": False, "message": msg, "retcode": None}

        ready, ready_msg = self._symbol_ready(mt5)
        if not ready:
            return {"ok": False, "message": ready_msg, "retcode": None}

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "message": f"No live tick available for {self.symbol}.", "retcode": None}

        direction = signal.action.upper()
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if direction == "BUY" else tick.bid)
        volume = self._normalize_volume(mt5, signal.volume)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": int(self.rules.get("deviation", 30) or 30),
            "magic": MAGIC,
            "comment": "TradeSmart Agent",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "message": f"order_send returned None: {mt5.last_error()}", "request": request}

        data = result._asdict() if hasattr(result, "_asdict") else dict(result)
        retcode = int(data.get("retcode", 0) or 0)
        success_codes = {int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)), int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
        ok = retcode in success_codes

        if retcode == 10017:
            message = "Trade failed: MT5 says trading is disabled. Check Algo Trading, broker permissions, and main trading password."
        elif ok:
            message = f"{direction} {self.symbol} placed successfully."
        else:
            message = f"Trade failed. Retcode: {retcode}"

        return {"ok": ok, "message": message, "retcode": retcode, "request": request, "result": data}

    def _close_position(self, mt5, ticket: Any) -> Dict[str, Any]:
        target = None
        for pos in self._positions(mt5):
            if str(pos.get("ticket")) == str(ticket):
                target = pos
                break

        if target is None:
            return {"ok": False, "message": f"Position {ticket} was not found.", "retcode": None}

        allowed, msg = self._terminal_trade_allowed(mt5)
        if not allowed:
            return {"ok": False, "message": msg, "retcode": None}

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "message": f"No live tick available for {self.symbol}.", "retcode": None}

        pos_type = int(target.get("type", 0) or 0)
        close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_price = float(tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(target.get("ticket")),
            "symbol": self.symbol,
            "volume": float(target.get("volume", 0.01) or 0.01),
            "type": close_type,
            "price": close_price,
            "deviation": int(self.rules.get("deviation", 30) or 30),
            "magic": MAGIC,
            "comment": "TradeSmart Agent Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "message": f"close order_send returned None: {mt5.last_error()}", "request": request}

        data = result._asdict() if hasattr(result, "_asdict") else dict(result)
        retcode = int(data.get("retcode", 0) or 0)
        success_codes = {int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)), int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))}
        ok = retcode in success_codes
        return {
            "ok": ok,
            "message": "Trade closed successfully." if ok else f"Close failed. Retcode: {retcode}",
            "retcode": retcode,
            "request": request,
            "result": data,
        }

    def _max_loss_hit(self, account_snapshot: Dict[str, Any]) -> Tuple[bool, float]:
        max_loss = float(self.rules.get("max_daily_loss_amount", 0) or 0)
        if max_loss <= 0:
            return False, 0.0
        balance = float(account_snapshot.get("balance", 0) or 0)
        equity = float(account_snapshot.get("equity", balance) or balance)
        loss = max(0.0, balance - equity)
        return loss >= max_loss, round(loss, 2)


    def _entry_cooldown_seconds(self) -> int:
        """
        Entry cooldown is intentionally disabled.

        TradeSmart still prevents duplicate entries on the same fully closed M1
        candle with `last_entry_candle_time`, and still respects Max Open Trades.
        If you ever want a delay again, return a positive number here and update
        `_entry_cooldown_block`.
        """
        return 0

    def _entry_cooldown_block(self, account_state: Dict[str, Any]) -> Tuple[bool, int]:
        """No time-based cooldown. Strategy + max open trades control entries."""
        return False, 0


    def _mark_entry_attempt(self, account_state: Dict[str, Any], signal: TradeSignal, candle_time: int) -> None:
        """Save the order attempt before sending so refresh loops cannot double-fire."""
        now = datetime.now(timezone.utc)
        account_state["last_entry_attempt_epoch"] = now.timestamp()
        account_state["last_entry_attempt_time"] = now.isoformat()
        account_state["last_entry_attempt_action"] = signal.action
        if candle_time:
            account_state["last_entry_attempt_candle_time"] = candle_time

    # ---------- main cycle ----------
    def run_cycle(self, execution_enabled: bool = False) -> Dict[str, Any]:
        ok, message, account = self._connect()
        if not ok:
            return {"ok": False, "phase": "connect", "event": "Connection Failed", "message": message, "thinking": message}

        mt5, _ = self._mt5()

        try:
            ready, ready_msg = self._symbol_ready(mt5)
            positions = self._positions(mt5)
            snapshot = self._account_snapshot(account or {}, positions)
            rates = self._rates(mt5, 120)
            last_closed = rates[-2] if len(rates) >= 2 else {}
            neutral_inputs = self._load_neutral_inputs()

            result: Dict[str, Any] = {
                "ok": True,
                "phase": "scan",
                "event": "Strategy Scan",
                "message": "TradeSmart scanned XAUUSD.",
                "thinking": "Reading XAUUSD M1 candles, account equity, open positions, and active strategy rules.",
                "symbol": self.symbol,
                "mode": self.rules.get("mode", self.profile.get("mode", "Demo")),
                "account": snapshot,
                "last_closed_m1": last_closed,
                "open_positions_count": len(positions),
                "positions": positions,
                "position_summary": self._position_summary(positions, rates),
                "decision": {"action": "NONE", "symbol": self.symbol, "reason": "No decision yet."},
                "strategy": None,
                "strategy_info": {},
                "inputs": neutral_inputs,
                "execution_enabled": execution_enabled,
                "order_sent": False,
                "order_result": None,
                "risk_blocks": [],
                "max_daily_loss_reached": False,
            }

            if not ready:
                result.update({"event": "Symbol Blocked", "message": ready_msg, "thinking": ready_msg})
                return result

            max_loss_hit, live_loss = self._max_loss_hit(snapshot)
            if max_loss_hit:
                result["max_daily_loss_reached"] = True
                result["risk_blocks"].append(f"Max Daily Loss Amount reached: ${live_loss}")
                result["event"] = "Max Loss Limit Reached"
                result["message"] = f"Max daily loss limit reached: ${live_loss}. Agent stopped and new trades are blocked."
                result["thinking"] = f"Risk lock triggered. Current equity drawdown from balance is ${live_loss}, which reached the max daily loss amount. Closing TradeSmart positions and blocking new entries."

                closes = []
                if execution_enabled and positions:
                    for pos in positions:
                        closes.append(self._close_position(mt5, pos.get("ticket")))
                result["order_result"] = closes
                result["order_sent"] = any(c.get("ok") for c in closes)
                return result

            signal, info = self._strategy_signal(rates, positions, neutral_inputs)
            result["decision"] = asdict(signal)
            result["strategy"] = info.get("strategy")
            result["strategy_info"] = info
            thoughts = info.get("thoughts") or []
            result["thinking"] = " | ".join(thoughts[-4:]) or signal.reason
            result["message"] = signal.reason or result["message"]

            if info.get("loader_error"):
                result["strategy_loader_note"] = info.get("loader_error")

            state = self._load_state()
            key = self._state_key()
            account_state = state.setdefault(key, {})
            candle_time = int(last_closed.get("time", 0) or 0)

            if signal.action == "HOLD":
                result["event"] = "Tracking"
                result["message"] = signal.reason
                return result

            if signal.action == "CLOSE" and signal.close_ticket:
                result["event"] = "Exit Signal"
                if execution_enabled:
                    close_result = self._close_position(mt5, signal.close_ticket)
                    result["order_result"] = close_result
                    result["order_sent"] = bool(close_result.get("ok"))
                    result["message"] = close_result.get("message", signal.reason)
                    if close_result.get("ok"):
                        account_state["last_exit_time"] = datetime.now(timezone.utc).isoformat()
                        account_state["last_exit_ticket"] = signal.close_ticket
                        self._save_state(state)
                return result

            if signal.action not in {"BUY", "SELL"}:
                result["event"] = "Strategy Scan"
                return result

            max_open = int(self.rules.get("max_open_trades", 1) or 1)
            if len(positions) >= max_open:
                result["event"] = "Risk Blocked"
                result["message"] = f"Max open trades reached: {len(positions)}/{max_open}."
                result["thinking"] = "Open trade limit reached. No new order will be placed while the current TradeSmart position is active."
                return result


            last_entry_candle = int(account_state.get("last_entry_candle_time", 0) or 0)
            if candle_time and last_entry_candle == candle_time:
                result["event"] = "Tracking"
                result["message"] = "This M1 candle was already processed for entry."
                result["thinking"] = "The strategy already acted on this fully closed M1 candle. Waiting for the next fully closed M1 candle before another entry."
                return result

            if not execution_enabled:
                result["event"] = "Preview"
                result["message"] = f"{signal.action} setup found. Execution is off."
                return result

            # Mark the attempt before mt5.order_send for audit tracking.
            # Duplicate entries are blocked by max_open_trades and by the
            # last_entry_candle_time check below.
            self._mark_entry_attempt(account_state, signal, candle_time)
            self._save_state(state)

            order_result = self._send_order(mt5, signal)
            result["event"] = "Order Sent" if order_result.get("ok") else "Order Failed"
            result["order_sent"] = bool(order_result.get("ok"))
            result["order_result"] = order_result
            result["message"] = order_result.get("message", signal.reason)

            if order_result.get("ok"):
                now = datetime.now(timezone.utc)
                if candle_time:
                    account_state["last_entry_candle_time"] = candle_time
                account_state["last_entry_action"] = signal.action
                account_state["last_entry_time"] = now.isoformat()
                account_state["last_entry_epoch"] = now.timestamp()
                self._save_state(state)

            return result

        finally:
            self.disconnect()
