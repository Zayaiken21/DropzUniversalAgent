# frontend/tradesmart_agent.py
"""
TradeSmart execution agent.

This file is the execution-capable agent layer. The page collects settings/rules,
then calls TradeSmartAgent.run_cycle(). By default the agent scans and builds a
plan. It only sends MT5 orders when:
1. A strategy signal hook returns BUY or SELL.
2. The selected profile is connected/valid.
3. Risk checks pass.
4. execution_enabled=True.
5. Live mode also has allow_live_execution=True.

Keep your strategy logic inside get_strategy_signal() or replace it with your
own model/subagent later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from frontend.mt5_secure_store import (
    connect_mt5,
    get_mt5_orders,
    get_mt5_positions,
    place_market_order,
    shutdown_mt5,
)


@dataclass
class TradeSmartDecision:
    action: str = "NONE"  # NONE, BUY, SELL
    symbol: str = ""
    volume: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason: str = "No executable strategy signal yet."


class TradeSmartAgent:
    def __init__(self, profile: Dict[str, Any], rules: Dict[str, Any]):
        self.profile = profile
        self.rules = rules

    def get_strategy_signal(self) -> TradeSmartDecision:
        """
        Hook for your strategy/subagent.

        Replace this with your real signal engine later. To test Demo execution,
        pass rules["manual_signal"] like:
        {
            "action": "BUY",
            "symbol": "EURUSD",
            "volume": 0.01,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reason": "Manual demo test"
        }
        """
        signal = self.rules.get("manual_signal") or {}
        action = str(signal.get("action", "NONE")).upper()

        if action not in {"BUY", "SELL"}:
            return TradeSmartDecision()

        return TradeSmartDecision(
            action=action,
            symbol=str(signal.get("symbol", "")).strip(),
            volume=float(signal.get("volume", 0) or 0),
            stop_loss=float(signal.get("stop_loss", signal.get("sl", 0)) or 0),
            take_profit=float(signal.get("take_profit", signal.get("tp", 0)) or 0),
            reason=str(signal.get("reason", "Manual TradeSmart signal")),
        )

    def validate_risk(
        self,
        decision: TradeSmartDecision,
        account_info: Dict[str, Any],
        positions: List[Dict[str, Any]],
        orders: List[Dict[str, Any]],
    ) -> List[str]:
        blocks: List[str] = []

        if decision.action not in {"BUY", "SELL"}:
            blocks.append("No BUY/SELL signal available.")
            return blocks

        if not decision.symbol:
            blocks.append("Signal missing symbol.")

        if decision.volume <= 0:
            blocks.append("Signal volume must be greater than 0.")

        max_open = int(self.rules.get("max_open_trades", 1) or 1)
        if len(positions) >= max_open:
            blocks.append(f"Max open trades reached: {len(positions)}/{max_open}.")

        max_pos_percent = float(self.rules.get("max_position_size_percent", 100) or 100)
        if max_pos_percent <= 0:
            blocks.append("Max position size must be greater than 0.")

        if self.rules.get("mode") == "Live" and not self.rules.get("allow_live_execution"):
            blocks.append("Live execution is blocked until allow_live_execution=True.")

        return blocks

    def run_cycle(self, execution_enabled: bool = False) -> Dict[str, Any]:
        connected, message, account_info = connect_mt5(self.profile)
        if not connected:
            return {"ok": False, "phase": "connect", "message": message}

        positions = get_mt5_positions()
        orders = get_mt5_orders()
        decision = self.get_strategy_signal()
        risk_blocks = self.validate_risk(decision, account_info, positions, orders)

        plan = {
            "ok": True,
            "phase": "plan",
            "message": "TradeSmart Agent scanned MT5 and built an execution plan.",
            "mode": self.profile.get("mode", self.rules.get("mode", "Demo")),
            "account": {
                "login": account_info.get("login"),
                "server": account_info.get("server"),
                "balance": account_info.get("balance"),
                "equity": account_info.get("equity"),
                "currency": account_info.get("currency"),
            },
            "positions_count": len(positions),
            "pending_orders_count": len(orders),
            "decision": decision.__dict__,
            "risk_blocks": risk_blocks,
            "execution_enabled": execution_enabled,
            "order_sent": False,
            "order_result": None,
        }

        shutdown_mt5()

        if not execution_enabled:
            plan["message"] = "TradeSmart Agent scan complete. Execution is off, so no order was sent."
            return plan

        if risk_blocks:
            plan["ok"] = False
            plan["phase"] = "risk_blocked"
            plan["message"] = "TradeSmart Agent blocked execution because risk checks failed."
            return plan

        order = {
            "symbol": decision.symbol,
            "action": decision.action,
            "volume": decision.volume,
            "sl": decision.stop_loss,
            "tp": decision.take_profit,
            "comment": "TradeSmart Agent",
        }

        order_result = place_market_order(
            self.profile,
            order,
            allow_live=bool(self.rules.get("allow_live_execution", False)),
        )

        plan["phase"] = "execution"
        plan["order_sent"] = bool(order_result.get("ok"))
        plan["order_result"] = order_result
        plan["ok"] = bool(order_result.get("ok"))
        plan["message"] = order_result.get("message", "Execution attempted.")
        return plan
