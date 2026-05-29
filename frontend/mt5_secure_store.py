# frontend/mt5_secure_store.py
"""
Encrypted MT5 profile storage + bridge-safe MT5 access for DropzUniversal.

Important:
- Streamlit Cloud must NOT import MetaTrader5.
- This file routes MT5 calls through frontend.tradesmart_bridge_client when a bridge URL/token is saved
  or when DROPZ_USE_WINDOWS_BRIDGE=true.
- Direct local MetaTrader5 imports only happen on Windows/local fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DATA_DIR = Path("data")
STORE_FILE = DATA_DIR / "mt5_accounts.encrypted.json"
LEGACY_STORE_FILE = DATA_DIR / "mt5_accounts.json"
KEY_FILE = DATA_DIR / ".dropz_mt5.key"
LOG_FILE = DATA_DIR / "mt5_connection.log"

ALLOWED_SYMBOL = "XAUUSD"


def _bridge_enabled(profile: Optional[Dict[str, Any]] = None) -> bool:
    profile = profile or {}
    env_enabled = str(os.getenv("DROPZ_USE_WINDOWS_BRIDGE", "true")).strip().lower() in {"1", "true", "yes", "on"}
    has_profile_bridge = bool(profile.get("bridge_url") and profile.get("bridge_token"))
    has_env_bridge = bool(os.getenv("TRADESMART_BRIDGE_URL") and os.getenv("TRADESMART_BRIDGE_TOKEN"))
    return has_profile_bridge or has_env_bridge or env_enabled


def _with_bridge_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(profile or {})
    merged.setdefault("bridge_url", os.getenv("TRADESMART_BRIDGE_URL", ""))
    merged.setdefault("bridge_token", os.getenv("TRADESMART_BRIDGE_TOKEN", ""))
    return merged


def _log_mt5_event(event: str, payload: Dict[str, Any] | None = None) -> None:
    try:
        from datetime import datetime
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        safe_payload = dict(payload or {})
        for key in ("password", "bridge_token"):
            if key in safe_payload:
                safe_payload[key] = "***"
        line = json.dumps(
            {"ts": datetime.utcnow().isoformat(), "event": event, "payload": safe_payload},
            default=str,
        )
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except Exception:
            return str(value)
    return str(value)


def _normalize_role(role: str = "client") -> str:
    role = str(role or "client").strip().lower()
    if role in {"admin", "owner"}:
        return "ceo"
    if role not in {"client", "ceo"}:
        return "client"
    return role


def _hash_value(prefix: str, value: Any) -> str:
    raw = _safe_str(value).strip().lower()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _get_fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("Missing dependency: cryptography. Install it with: pip install cryptography") from exc

    env_key = os.getenv("DROPZ_MT5_FERNET_KEY") or os.getenv("TRADESMART_MASTER_KEY")
    if env_key:
        return Fernet(env_key.encode())

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return Fernet(KEY_FILE.read_bytes())

    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    return Fernet(key)


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        STORE_FILE.write_text("{}", encoding="utf-8")


def _read_store() -> Dict[str, Any]:
    _ensure_store()
    try:
        return json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_store(data: Dict[str, Any]) -> None:
    _ensure_store()
    STORE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _session_identity_values() -> List[Tuple[str, Any]]:
    values: List[Tuple[str, Any]] = []
    try:
        import streamlit as st

        user = st.session_state.get("user")
        if user:
            values.append(("user", user))
            if isinstance(user, dict):
                for key in (
                    "token", "client_token", "user_token", "id", "user_id",
                    "username", "email", "name", "client_name",
                ):
                    if user.get(key):
                        values.append((f"user.{key}", user.get(key)))

        for key in (
            "user_token", "client_token", "auth_token", "token",
            "user_id", "username", "email", "client_name", "name",
        ):
            value = st.session_state.get(key)
            if value:
                values.append((key, value))
    except Exception:
        pass

    deduped: List[Tuple[str, Any]] = []
    seen = set()
    for label, value in values:
        fingerprint = (label, _safe_str(value))
        if fingerprint not in seen:
            seen.add(fingerprint)
            deduped.append((label, value))
    return deduped


def get_signed_in_user_key(role: str = "client") -> str:
    identities = _session_identity_values()
    if identities:
        return _hash_value("user", identities[0][1])
    return _hash_value("user", "local_default_user")


def _old_role_key(role: str, label: str, value: Any) -> str:
    role = _normalize_role(role)
    raw = f"{role}:{label}:{_safe_str(value).strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{role}_{digest}"


def get_user_key_candidates(role: str = "client") -> List[str]:
    role = _normalize_role(role)
    candidates = [get_signed_in_user_key(role)]

    identities = _session_identity_values()
    for label, value in identities:
        candidates.append(_hash_value("user", value))
        candidates.append(_old_role_key("client", label, value))
        candidates.append(_old_role_key("ceo", label, value))
        candidates.append(_old_role_key(role, label, value))

    candidates.extend([
        _hash_value("user", "local_default_user"),
        "client_client", "ceo_ceo", "client_ceo", "ceo_client",
        "client", "ceo", role,
    ])

    deduped: List[str] = []
    for key in candidates:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def debug_user_identity(role: str = "client") -> Dict[str, Any]:
    try:
        import streamlit as st
        return {
            "normalized_role": _normalize_role(role),
            "primary_user_key": get_signed_in_user_key(role),
            "all_user_key_candidates": get_user_key_candidates(role),
            "available_session_keys": sorted(list(st.session_state.keys())),
            "user_session_preview": _safe_str(st.session_state.get("user"))[:700],
            "store_file": str(STORE_FILE.resolve()),
            "bridge_mode": True,
        }
    except Exception:
        return {
            "normalized_role": _normalize_role(role),
            "primary_user_key": get_signed_in_user_key(role),
            "all_user_key_candidates": get_user_key_candidates(role),
            "store_file": str(STORE_FILE.resolve()),
            "bridge_mode": True,
        }


def _blank_profile(mode: str) -> Dict[str, Any]:
    return {
        "mode": mode.title(),
        "login": "",
        "password": "",
        "server": "",
        "terminal_path": "",
        "timeout": 10000,
        "portable": False,
        "bridge_url": os.getenv("TRADESMART_BRIDGE_URL", ""),
        "bridge_token": os.getenv("TRADESMART_BRIDGE_TOKEN", ""),
        "saved": False,
        "source_user_key": "",
    }


def _encrypt_profile(profile: Dict[str, Any]) -> str:
    payload = json.dumps(profile).encode("utf-8")
    return _get_fernet().encrypt(payload).decode("utf-8")


def _decrypt_profile(token: str) -> Dict[str, Any]:
    payload = _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    return json.loads(payload)


def _clean_profile(profile: Dict[str, Any], mode: str) -> Dict[str, Any]:
    return {
        "mode": mode.title(),
        "login": str(profile.get("login", "")).strip(),
        "password": str(profile.get("password", "")),
        "server": str(profile.get("server", "")).strip(),
        "terminal_path": str(profile.get("terminal_path", "")).strip(),
        "timeout": int(profile.get("timeout", 10000) or 10000),
        "portable": bool(profile.get("portable", False)),
        "bridge_url": str(profile.get("bridge_url", os.getenv("TRADESMART_BRIDGE_URL", ""))).strip(),
        "bridge_token": str(profile.get("bridge_token", os.getenv("TRADESMART_BRIDGE_TOKEN", ""))),
    }


def _load_encrypted_by_key(user_key: str, mode: str) -> Optional[Dict[str, Any]]:
    data = _read_store()
    encrypted = data.get(user_key, {}).get("profiles", {}).get(mode.title())
    if not encrypted:
        return None
    profile = _decrypt_profile(encrypted)
    profile = _clean_profile(profile, mode)
    profile["saved"] = True
    profile["source_user_key"] = user_key
    return profile


def _profile_from_legacy(user_key: str, mode: str) -> Optional[Dict[str, Any]]:
    if not LEGACY_STORE_FILE.exists():
        return None
    try:
        data = json.loads(LEGACY_STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    raw = data.get(user_key)
    if not isinstance(raw, dict):
        return None

    mode = mode.title()
    nested = raw.get("profiles", {}).get(mode)
    if isinstance(nested, dict):
        profile = _clean_profile(nested, mode)
        profile["saved"] = True
        profile["source_user_key"] = user_key
        return profile

    if {"login", "password", "server"}.intersection(raw.keys()):
        raw_mode = str(raw.get("mode", "")).title()
        if raw_mode == mode:
            profile = _clean_profile(raw, mode)
            profile["saved"] = True
            profile["source_user_key"] = user_key
            return profile

    return None


def save_mt5_profile(user_key: str, mode: str, profile: Dict[str, Any]) -> None:
    mode = mode.title()
    if mode not in {"Demo", "Live"}:
        mode = "Demo"

    primary = user_key or get_signed_in_user_key()
    clean = _clean_profile(profile, mode)

    data = _read_store()
    bucket = data.setdefault(primary, {})
    bucket.setdefault("profiles", {})[mode] = _encrypt_profile(clean)
    bucket["active_mode"] = mode
    _write_store(data)


def save_mt5_profile_for_current_user(mode: str, profile: Dict[str, Any], role: str = "client") -> str:
    key = get_signed_in_user_key(role)
    save_mt5_profile(key, mode, profile)
    return key


def load_mt5_profile(user_key: str = "", mode: str = "Demo", role: str = "client") -> Dict[str, Any]:
    mode = mode.title()
    if mode not in {"Demo", "Live"}:
        mode = "Demo"

    primary = user_key or get_signed_in_user_key(role)
    candidates = [primary] + [k for k in get_user_key_candidates(role) if k != primary]

    decrypt_error = None
    for candidate in candidates:
        try:
            profile = _load_encrypted_by_key(candidate, mode)
        except Exception:
            decrypt_error = "A saved MT5 profile was found but could not be decrypted. Keep the same data/.dropz_mt5.key file or resave credentials."
            continue

        if profile and (profile.get("login") or profile.get("password") or profile.get("server") or profile.get("bridge_url")):
            if candidate != primary:
                save_mt5_profile(primary, mode, profile)
                profile["source_user_key"] = primary
            return _with_bridge_defaults(profile)

    for candidate in candidates:
        legacy = _profile_from_legacy(candidate, mode)
        if legacy and (legacy.get("login") or legacy.get("password") or legacy.get("server") or legacy.get("bridge_url")):
            save_mt5_profile(primary, mode, legacy)
            legacy["source_user_key"] = primary
            return _with_bridge_defaults(legacy)

    blank = _blank_profile(mode)
    if decrypt_error:
        blank["error"] = decrypt_error
    return _with_bridge_defaults(blank)


def get_active_mt5_mode(user_key: str = "", role: str = "client") -> str:
    key = user_key or get_signed_in_user_key()
    data = _read_store()

    for candidate in [key] + [k for k in get_user_key_candidates(role) if k != key]:
        mode = data.get(candidate, {}).get("active_mode")
        if mode in {"Demo", "Live"}:
            if candidate != key:
                set_active_mt5_mode(key, mode)
            return mode

    return "Demo"


def set_active_mt5_mode(user_key: str = "", mode: str = "Demo") -> None:
    key = user_key or get_signed_in_user_key()
    mode = mode.title()
    if mode not in {"Demo", "Live"}:
        mode = "Demo"

    data = _read_store()
    data.setdefault(key, {}).setdefault("profiles", {})
    data[key]["active_mode"] = mode
    _write_store(data)


def mask_login(login: str) -> str:
    login = str(login or "")
    if not login:
        return "Not saved"
    if len(login) <= 4:
        return "*" * len(login)
    return f"{'*' * (len(login) - 4)}{login[-4:]}"


def password_status(password: str) -> str:
    return "Saved" if str(password or "") else "Not saved"


def profile_fingerprint(profile: Dict[str, Any]) -> str:
    raw = (
        f"{profile.get('mode','')}|{profile.get('login','')}|{profile.get('server','')}|"
        f"{bool(profile.get('password'))}|{profile.get('terminal_path','')}|"
        f"{profile.get('bridge_url','')}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def clear_mt5_profile(user_key: str, mode: str) -> None:
    mode = mode.title()
    data = _read_store()
    if user_key in data and isinstance(data[user_key], dict):
        profiles = data[user_key].setdefault("profiles", {})
        profiles.pop(mode, None)
        _write_store(data)


def is_profile_ready(profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    # For bridge mode, MT5 credentials may live inside the Windows bridge .env.
    # Keep old checks for your settings UI, but allow bridge-only profiles to connect.
    bridge_url = profile.get("bridge_url") or os.getenv("TRADESMART_BRIDGE_URL")
    bridge_token = profile.get("bridge_token") or os.getenv("TRADESMART_BRIDGE_TOKEN")
    if bridge_url and bridge_token:
        return True, []

    if not profile.get("login"):
        missing.append("MT5 Login")
    if not profile.get("password"):
        missing.append("MT5 Password")
    if not profile.get("server"):
        missing.append("MT5 Server")
    return len(missing) == 0, missing


def _bridge_error_message(data: Dict[str, Any]) -> str:
    detail = data.get("detail")
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return detail.get("message") or json.dumps(detail)
    return data.get("message") or data.get("error") or "Windows Bridge request failed."


def connect_mt5(profile: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    profile = _with_bridge_defaults(profile)
    _log_mt5_event("connect_attempt", {
        "mode": profile.get("mode"),
        "login": profile.get("login"),
        "server": profile.get("server"),
        "bridge_url": profile.get("bridge_url"),
        "bridge_mode": _bridge_enabled(profile),
    })

    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import connect_bridge
            ok, data = connect_bridge(profile)
            if not ok:
                msg = _bridge_error_message(data)
                _log_mt5_event("bridge_connect_failed", {"message": msg})
                return False, msg, None
            account = data.get("account") or {}
            _log_mt5_event("bridge_connect_success", {
                "returned_login": account.get("login"),
                "returned_server": account.get("server"),
            })
            return True, "Connected through Windows Bridge.", account
        except Exception as exc:
            return False, f"Bridge connection failed: {exc}", None

    ready, missing = is_profile_ready(profile)
    if not ready:
        return False, f"Missing required MT5 fields: {', '.join(missing)}.", None

    if platform.system() != "Windows":
        return False, "MetaTrader5 is not available here. Use the Windows Bridge instead.", None

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return False, "MetaTrader5 package is not installed. Run it only on Windows or use the Windows Bridge.", None

    kwargs = {
        "login": int(profile["login"]),
        "password": profile["password"],
        "server": profile["server"],
        "timeout": int(profile.get("timeout", 10000) or 10000),
        "portable": bool(profile.get("portable", False)),
    }
    if profile.get("terminal_path"):
        kwargs["path"] = profile["terminal_path"]

    try:
        mt5.shutdown()
    except Exception:
        pass

    if not mt5.initialize(**kwargs):
        err = mt5.last_error()
        detail = ""
        if isinstance(err, tuple) and len(err) >= 2 and str(err[0]) == "-6":
            detail = " Authorization failed. Check login, password, server, and Demo/Live account type."
        return False, f"MT5 initialization failed: {err}.{detail}", None

    account_info = mt5.account_info()
    if account_info is None:
        err = mt5.last_error()
        mt5.shutdown()
        return False, f"MT5 account_info failed: {err}", None

    return True, "MT5 connected successfully.", account_info._asdict()


def get_mt5_positions(profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    profile = _with_bridge_defaults(profile or {})
    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import bridge_request
            ok, data = bridge_request(profile, "/positions", payload=None, timeout=10)
            return data.get("positions", []) if ok else []
        except Exception:
            return []

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []
    positions = mt5.positions_get(symbol=ALLOWED_SYMBOL)
    return [] if positions is None else [p._asdict() for p in positions]


def get_mt5_orders(profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    profile = _with_bridge_defaults(profile or {})
    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import bridge_request
            ok, data = bridge_request(profile, "/orders", payload=None, timeout=10)
            return data.get("orders", []) if ok else []
        except Exception:
            return []

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []
    orders = mt5.orders_get(symbol=ALLOWED_SYMBOL)
    return [] if orders is None else [o._asdict() for o in orders]


def get_mt5_rates(profile: Dict[str, Any], timeframe: str = "M1", count: int = 100) -> List[Dict[str, Any]]:
    profile = _with_bridge_defaults(profile)
    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import bridge_request
            ok, data = bridge_request(
                profile,
                "/rates",
                payload={"symbol": ALLOWED_SYMBOL, "timeframe": timeframe, "count": count},
                timeout=12,
            )
            return data.get("rates", []) if ok else []
        except Exception:
            return []

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []

    tf = getattr(mt5, f"TIMEFRAME_{str(timeframe).upper()}", mt5.TIMEFRAME_M1)
    raw = mt5.copy_rates_from_pos(ALLOWED_SYMBOL, tf, 0, int(count or 100))
    rows: List[Dict[str, Any]] = []
    if raw is not None:
        for r in raw:
            try:
                rows.append({
                    "time": int(r["time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "tick_volume": int(r["tick_volume"]),
                    "spread": int(r["spread"]),
                    "real_volume": int(r["real_volume"]),
                })
            except Exception:
                rows.append(dict(r))
    return rows


def disconnect_mt5(profile: Optional[Dict[str, Any]] = None) -> None:
    profile = _with_bridge_defaults(profile or {})
    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import disconnect_bridge
            disconnect_bridge(profile)
            return
        except Exception:
            return
    shutdown_mt5()


def shutdown_mt5() -> None:
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass


def build_order_preview(symbol: str, volume: float, direction: str, sl: float = 0.0, tp: float = 0.0) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "volume": volume,
        "direction": direction,
        "stop_loss": sl,
        "take_profit": tp,
        "status": "Preview only - no trade placed",
    }


def account_matches_profile(account_info: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    if not account_info:
        return False

    # Bridge mode may connect using credentials stored inside the Windows bridge .env.
    # If the profile does not include a login/server, trust the bridge account payload.
    if profile.get("bridge_url") and not profile.get("login"):
        return True

    requested_login = str(profile.get("login", "")).strip()
    returned_login = str(account_info.get("login", "")).strip()
    requested_server = str(profile.get("server", "")).strip().lower()
    returned_server = str(account_info.get("server", "")).strip().lower()
    return bool(
        requested_login
        and returned_login
        and requested_login == returned_login
        and (
            not requested_server
            or not returned_server
            or requested_server in returned_server
            or returned_server in requested_server
        )
    )


def place_market_order(profile: Dict[str, Any], order: Dict[str, Any], allow_live: bool = False) -> Dict[str, Any]:
    profile = _with_bridge_defaults(profile)
    mode = str(profile.get("mode", "Demo")).title()
    if mode == "Live" and not allow_live:
        return {"ok": False, "message": "Live order blocked. Set allow_live=True only after all live risk checks are approved."}

    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import place_xauusd_order

            ok, data = place_xauusd_order(profile, {
                "direction": order.get("action") or order.get("direction"),
                "volume": float(order.get("volume", 0)),
                "stop_loss": float(order.get("sl", order.get("stop_loss", 0)) or 0),
                "take_profit": float(order.get("tp", order.get("take_profit", 0)) or 0),
                "reason": order.get("comment", "TradeSmart Agent"),
            })

            if not ok:
                return {"ok": False, "message": _bridge_error_message(data), "result": data}

            return {
                "ok": True,
                "message": "Order placed through Windows Bridge.",
                "account": data.get("account", {}),
                "result": data.get("result", data),
            }

        except Exception as exc:
            return {"ok": False, "message": f"Bridge execution failed: {exc}"}

    connected, message, account_info = connect_mt5(profile)
    if not connected:
        return {"ok": False, "message": message, "phase": "connect"}

    try:
        import MetaTrader5 as mt5
    except ImportError:
        shutdown_mt5()
        return {"ok": False, "message": "MetaTrader5 package is not installed."}

    symbol = str(order.get("symbol", ALLOWED_SYMBOL)).strip() or ALLOWED_SYMBOL
    action = str(order.get("action", order.get("direction", ""))).upper().strip()
    volume = float(order.get("volume", 0) or 0)
    sl = float(order.get("sl", order.get("stop_loss", 0)) or 0)
    tp = float(order.get("tp", order.get("take_profit", 0)) or 0)
    deviation = int(order.get("deviation", 20) or 20)
    magic = int(order.get("magic", 777001) or 777001)
    comment = str(order.get("comment", "TradeSmart Agent"))[:31]

    if symbol.upper() != ALLOWED_SYMBOL:
        shutdown_mt5()
        return {"ok": False, "message": "Only XAUUSD is allowed."}

    if action not in {"BUY", "SELL"} or volume <= 0:
        shutdown_mt5()
        return {"ok": False, "message": "Invalid order. Required: BUY/SELL action and volume > 0."}

    if not mt5.symbol_select(symbol, True):
        err = mt5.last_error()
        shutdown_mt5()
        return {"ok": False, "message": f"Could not select MT5 symbol {symbol}: {err}"}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        err = mt5.last_error()
        shutdown_mt5()
        return {"ok": False, "message": f"No tick data for {symbol}: {err}"}

    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if action == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
    }

    if sl > 0:
        request["sl"] = sl
    if tp > 0:
        request["tp"] = tp

    last_result = None
    for filling in [
        getattr(mt5, "ORDER_FILLING_IOC", None),
        getattr(mt5, "ORDER_FILLING_FOK", None),
        getattr(mt5, "ORDER_FILLING_RETURN", None),
    ]:
        if filling is None:
            continue
        request["type_filling"] = filling
        result = mt5.order_send(request)
        if result is None:
            last_result = {"message": f"MT5 order_send returned None: {mt5.last_error()}", "request": request}
            continue

        result_dict = result._asdict()
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            shutdown_mt5()
            return {
                "ok": True,
                "message": "Order placed.",
                "account": {
                    "login": account_info.get("login"),
                    "server": account_info.get("server"),
                    "balance": account_info.get("balance"),
                    "equity": account_info.get("equity"),
                    "currency": account_info.get("currency"),
                },
                "request": request,
                "result": result_dict,
            }
        last_result = result_dict

    shutdown_mt5()
    return {"ok": False, "message": "Order rejected.", "request": request, "result": last_result}


def close_market_position(profile: Dict[str, Any], ticket: int, volume: Optional[float] = None, comment: str = "TradeSmart Close") -> Dict[str, Any]:
    profile = _with_bridge_defaults(profile)
    if _bridge_enabled(profile):
        try:
            from frontend.tradesmart_bridge_client import bridge_request
            payload = {"ticket": int(ticket), "symbol": ALLOWED_SYMBOL, "comment": comment}
            if volume is not None:
                payload["volume"] = float(volume)
            ok, data = bridge_request(profile, "/close_position", payload=payload, timeout=20)
            if not ok:
                return {"ok": False, "message": _bridge_error_message(data), "result": data}
            return {"ok": True, "message": "Position closed through Windows Bridge.", "result": data, "account": data.get("account", {})}
        except Exception as exc:
            return {"ok": False, "message": f"Bridge close failed: {exc}"}
    return {"ok": False, "message": "Direct close is not implemented in cloud mode. Use the Windows Bridge."}


def run_tradesmart_agent_cycle(profile: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    connected, message, account_info = connect_mt5(profile)
    if not connected:
        return {"ok": False, "message": message, "phase": "connect"}

    positions = get_mt5_positions(profile)
    orders = get_mt5_orders(profile)

    max_open_trades = int(rules.get("max_open_trades", 1) or 1)
    can_consider_new_trade = len(positions) < max_open_trades

    return {
        "ok": True,
        "phase": "scan",
        "message": "TradeSmart Agent scanned MT5 through the active connection.",
        "account": {
            "login": account_info.get("login"),
            "server": account_info.get("server"),
            "balance": account_info.get("balance"),
            "equity": account_info.get("equity"),
            "currency": account_info.get("currency"),
        } if account_info else {},
        "positions_count": len(positions),
        "pending_orders_count": len(orders),
        "can_consider_new_trade": can_consider_new_trade,
        "rules": rules,
    }
