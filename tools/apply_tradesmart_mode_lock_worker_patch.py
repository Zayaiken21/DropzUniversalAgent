
from __future__ import annotations

from pathlib import Path

TARGET = Path("frontend/tradesmart_page.py")

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[ok] {label} already patched")
        return text
    if old not in text:
        raise RuntimeError(f"Could not find block for: {label}")
    print(f"[patch] {label}")
    return text.replace(old, new, 1)

def main() -> None:
    path = TARGET
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run this from your DropzUniversalAgent root folder.")

    text = path.read_text(encoding="utf-8")

    if "TRADESMART_WORKER_STATE_FILE" not in text:
        text = text.replace(
            "from datetime import datetime\nfrom html import escape\nimport re\nfrom typing import Any, Dict, List, Optional\n",
            "from datetime import datetime\nfrom html import escape\nimport json\nfrom pathlib import Path\nimport re\nfrom typing import Any, Dict, List, Optional\n",
            1,
        )

        text = text.replace(
            "TRADESMART_OUTPUT_LIMIT = 50\n",
            """TRADESMART_OUTPUT_LIMIT = 50
TRADESMART_WORKER_STATE_FILE = Path("data/tradesmart_worker_state.json")


def _save_tradesmart_worker_state(
    *,
    enabled: bool,
    mode: str,
    profile: Dict[str, Any],
    risk: Dict[str, Any],
    user_key: str,
) -> None:
    \"\"\"Persist the TradeSmart run state for agents/tradesmart_worker.py.\"\"\"
    TRADESMART_WORKER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(enabled),
        "mode": str(mode or "Demo"),
        "symbol": SYMBOL,
        "user_key": user_key,
        "profile": dict(profile or {}),
        "risk": dict(risk or {}),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    TRADESMART_WORKER_STATE_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

""",
            1,
        )
        print("[patch] worker state helper added")
    else:
        print("[ok] worker state helper already exists")

    old_mode = """    mode_key = f"tradesmart_mode_{user_key}"
    mode = st.radio("TradeSmart MT5 Mode", ["Demo", "Live"], horizontal=True, key=mode_key)
    profile = _load_mt5_profile(mode)
"""
    new_mode = """    connected_key = f"tradesmart_connected_{user_key}"
    connected_mode_key = f"tradesmart_connected_mode_{user_key}"
    active_connected_mode = st.session_state.get(connected_mode_key)
    connected_now = bool(st.session_state.get(connected_key)) and active_connected_mode in ("Demo", "Live")

    mode_key = f"tradesmart_mode_{user_key}"
    if connected_now:
        # Lock Demo/Live while connected. Users must disconnect before switching.
        st.session_state[mode_key] = active_connected_mode

    mode = st.radio(
        "TradeSmart MT5 Mode",
        ["Demo", "Live"],
        horizontal=True,
        key=mode_key,
        disabled=connected_now,
        index=0 if st.session_state.get(mode_key, "Demo") != "Live" else 1,
    )

    if connected_now:
        mode = active_connected_mode
        st.info(f"{active_connected_mode} is currently connected. Disconnect before switching Demo/Live mode.")

    profile = _load_mt5_profile(mode)
"""
    text = replace_once(text, old_mode, new_mode, "Demo/Live radio lock")

    old_connected = """    connected_key = f"tradesmart_connected_{user_key}"
    connected_mode_key = f"tradesmart_connected_mode_{user_key}"
    active_connected_mode = st.session_state.get(connected_mode_key)

    # Only one selected MT5 profile can be active on the page at a time.
    # If the user switches Demo/Live, never reuse the old account snapshot.
    if bool(st.session_state.get(connected_key)) and active_connected_mode and active_connected_mode != mode:
        st.session_state[connected_key] = False
        st.session_state[connected_mode_key] = None
        connected = False
    else:
        connected = bool(st.session_state.get(connected_key)) and active_connected_mode == mode

"""
    new_connected = """    connected = bool(st.session_state.get(connected_key)) and active_connected_mode == mode

"""
    if old_connected in text:
        text = text.replace(old_connected, new_connected, 1)
        print("[patch] removed auto-disconnect-on-mode-switch")
    else:
        print("[ok] auto-disconnect block not found or already removed")

    old_disconnect = """                st.session_state[connected_key] = False
                st.session_state[connected_mode_key] = None
                _add_log("Disconnected", f"Disconnected from {mode} MT5.")
                st.rerun()
"""
    new_disconnect = """                st.session_state[connected_key] = False
                st.session_state[connected_mode_key] = None
                _save_tradesmart_worker_state(
                    enabled=False,
                    mode=mode,
                    profile=profile,
                    risk={},
                    user_key=user_key,
                )
                _add_log("Disconnected", f"Disconnected from {mode} MT5.")
                st.rerun()
"""
    if old_disconnect in text:
        text = text.replace(old_disconnect, new_disconnect, 1)
        print("[patch] worker disabled on disconnect")
    else:
        print("[ok] disconnect block not found or already patched")

    old_risk = """    risk = {
        "trade_volume": float(trade_volume),
        "max_open_trades": int(max_open_trades),
        "max_daily_loss_amount": float(max_daily_loss_amount),
        "ai_instructions": ai_instructions,
        "allow_live_execution": mode == "Live",
        "entry_cooldown_seconds": 60,
        "check_interval_seconds": TRADESMART_CHECK_INTERVAL_SECONDS,
    }

    _section("Live Trade Tracking")
"""
    new_risk = """    risk = {
        "trade_volume": float(trade_volume),
        "max_open_trades": int(max_open_trades),
        "max_daily_loss_amount": float(max_daily_loss_amount),
        "ai_instructions": ai_instructions,
        "allow_live_execution": mode == "Live",
        "entry_cooldown_seconds": 60,
        "check_interval_seconds": TRADESMART_CHECK_INTERVAL_SECONDS,
    }

    _save_tradesmart_worker_state(
        enabled=bool(agent_enabled and connected),
        mode=mode,
        profile=profile,
        risk=risk,
        user_key=user_key,
    )

    _section("Live Trade Tracking")
"""
    text = replace_once(text, old_risk, new_risk, "worker state save after risk settings")

    path.write_text(text, encoding="utf-8")
    print("[done] frontend/tradesmart_page.py patched successfully.")

if __name__ == "__main__":
    main()
