from __future__ import annotations

from typing import Any, Dict, Tuple

def _local_only() -> Tuple[bool, Dict[str, Any]]:
    return False, {
        "message": (
            "TradeSmart Desktop runs MT5 locally. The cloud bridge/relay/ngrok "
            "connector is disabled in this build."
        )
    }

def connect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def disconnect_bridge(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return True, {"ok": True, "message": "Local desktop mode does not use the bridge."}

def get_bridge_status(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def get_bridge_positions(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def get_bridge_orders(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def get_bridge_rates(settings: Dict[str, Any], timeframe: str = "M1", count: int = 100) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def place_xauusd_order(settings: Dict[str, Any], signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()

def close_xauusd_position(settings: Dict[str, Any], ticket: int) -> Tuple[bool, Dict[str, Any]]:
    return _local_only()
