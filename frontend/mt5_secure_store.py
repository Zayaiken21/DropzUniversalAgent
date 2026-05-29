# frontend/mt5_secure_store.py
"""
Encrypted MT5 profile storage for DropzUniversal.

Important design choice:
- The primary profile key is ROLE-INDEPENDENT: user_<hash>.
- Demo and Live are stored separately under the same signed-in user.
- Loader also checks old client_/ceo_ keys so previous saves can be recovered.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DATA_DIR = Path("data")
STORE_FILE = DATA_DIR / "mt5_accounts.encrypted.json"
LEGACY_STORE_FILE = DATA_DIR / "mt5_accounts.json"
KEY_FILE = DATA_DIR / ".dropz_mt5.key"
LOG_FILE = DATA_DIR / "mt5_connection.log"



def _log_mt5_event(event: str, payload: Dict[str, Any] | None = None) -> None:
    """Write MT5 connection/execution diagnostics to data/mt5_connection.log instead of the frontend."""
    try:
        from datetime import datetime
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        safe_payload = dict(payload or {})
        if "password" in safe_payload:
            safe_payload["password"] = "***"
        line = json.dumps(
            {
                "ts": datetime.utcnow().isoformat(),
                "event": event,
                "payload": safe_payload,
            },
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
    """
    Primary key used by both Settings and TradeSmart.
    It intentionally does NOT include role, so CEO/Client pages read the same signed-in user's MT5 profile.
    """
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
    """
    Checks current role-independent key first, then old client_/ceo_ keys,
    then old static keys from earlier patches.
    """
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
        }
    except Exception:
        return {
            "normalized_role": _normalize_role(role),
            "primary_user_key": get_signed_in_user_key(role),
            "all_user_key_candidates": get_user_key_candidates(role),
            "store_file": str(STORE_FILE.resolve()),
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
    """Normalize MT5 credentials exactly before saving/connecting.

    MT5 is strict: invisible spaces, copied quotes, or a stale terminal path can
    make Demo fail while Live works. This keeps Demo/Live separated but cleans
    the values MT5 actually receives.
    """
    raw_login = str(profile.get("login", "") or "").strip().replace("\\ufeff", "")
    login = re.sub(r"\\D+", "", raw_login)

    password = str(profile.get("password", "") or "").replace("\\ufeff", "").strip()
    server = str(profile.get("server", "") or "").replace("\\ufeff", "").replace("\\u00a0", " ").strip().strip('"').strip("'")
    server = re.sub(r"\\s+", " ", server)

    terminal_path = str(profile.get("terminal_path", "") or "").replace("\\ufeff", "").strip().strip('"').strip("'")

    try:
        timeout = int(profile.get("timeout", 8000) or 8000)
    except Exception:
        timeout = 8000
    timeout = max(5000, min(timeout, 20000))

    return {
        "mode": mode.title(),
        "login": login,
        "password": password,
        "server": server,
        "terminal_path": terminal_path,
        "timeout": timeout,
        "portable": bool(profile.get("portable", False)),
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
        # Older flat format can be dangerous because it may contain only the last-used account.
        # Only migrate it when the old record explicitly says it belongs to this exact mode.
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

    # Important:
    # If the user previously saved credentials under an older candidate key
    # (client_/ceo_/legacy/default), those stale records can be discovered by
    # load_mt5_profile(). Remove this mode from every known candidate before
    # writing the fresh profile under the current primary key.
    for candidate in get_user_key_candidates():
        bucket = data.get(candidate)
        if isinstance(bucket, dict):
            profiles = bucket.get("profiles")
            if isinstance(profiles, dict):
                profiles.pop(mode, None)

    bucket = data.setdefault(primary, {})
    bucket.setdefault("profiles", {})[mode] = _encrypt_profile(clean)
    bucket["active_mode"] = mode
    _write_store(data)


def save_mt5_profile_for_current_user(mode: str, profile: Dict[str, Any], role: str = "client") -> str:
    """
    Saves once under the new role-independent key.
    Returns the key used.
    """
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

        if profile and (profile.get("login") or profile.get("password") or profile.get("server")):
            if candidate != primary:
                save_mt5_profile(primary, mode, profile)
                profile["source_user_key"] = primary
            return profile

    for candidate in candidates:
        legacy = _profile_from_legacy(candidate, mode)
        if legacy and (legacy.get("login") or legacy.get("password") or legacy.get("server")):
            save_mt5_profile(primary, mode, legacy)
            legacy["source_user_key"] = primary
            return legacy

    blank = _blank_profile(mode)
    if decrypt_error:
        blank["error"] = decrypt_error
    return blank


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
    """Short non-secret fingerprint for widget refresh and connection state."""
    raw = f"{profile.get('mode','')}|{profile.get('login','')}|{profile.get('server','')}|{bool(profile.get('password'))}|{profile.get('terminal_path','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def clear_mt5_profile(user_key: str, mode: str) -> None:
    """Remove only the selected Demo/Live profile for this signed-in user.

    Clears the current key and all known legacy/candidate keys so an older
    profile cannot reappear after the user presses Clear.
    """
    mode = mode.title()
    data = _read_store()
    keys_to_clear = [user_key] + [k for k in get_user_key_candidates() if k != user_key]

    changed = False
    for key in keys_to_clear:
        bucket = data.get(key)
        if isinstance(bucket, dict):
            profiles = bucket.get("profiles")
            if isinstance(profiles, dict) and mode in profiles:
                profiles.pop(mode, None)
                changed = True

    if changed:
        _write_store(data)

def is_profile_ready(profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    if not profile.get("login"):
        missing.append("MT5 Login")
    if not profile.get("password"):
        missing.append("MT5 Password")
    if not profile.get("server"):
        missing.append("MT5 Server")
    return len(missing) == 0, missing


def _mt5_error_detail(err: Any) -> str:
    code = None
    msg = ""
    if isinstance(err, tuple) and err:
        code = str(err[0])
        msg = str(err[1]) if len(err) > 1 else ""
    else:
        msg = str(err)

    if code == "-6" or "Authorization failed" in msg:
        return (
            " Authorization failed usually means the selected Demo/Live profile has an invalid login, "
            "wrong password, wrong broker server, or the account does not belong to that server. "
            "Demo and Live often use different server names. The app sent the saved selected-mode credentials to MT5."
        )
    if code == "-10001" or "IPC" in msg:
        return (
            " IPC send failed usually means the MT5 terminal process is stuck or already locked by another session. "
            "The app will retry once with a clean initialize/login sequence."
        )
    return ""


def connect_mt5(profile: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    # Always clean at connect time too, so Settings, Dashboard, and TradeSmart
    # all send MT5 the same selected Demo/Live credential format.
    profile = _clean_profile(profile or {}, str((profile or {}).get("mode", "Demo")))

    _log_mt5_event("connect_attempt", {
        "mode": profile.get("mode"),
        "login": profile.get("login"),
        "server": profile.get("server"),
        "terminal_path": profile.get("terminal_path"),
        "portable": profile.get("portable"),
        "timeout": profile.get("timeout"),
    })

    ready, missing = is_profile_ready(profile)
    if not ready:
        return False, f"Missing required MT5 fields: {', '.join(missing)}.", None

    if platform.system() != "Windows":
        return False, "MetaTrader5 Python connections normally require Windows with the MT5 desktop terminal installed.", None

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return False, "MetaTrader5 package is not installed. Run: pip install MetaTrader5", None

    login = int(profile["login"])
    password = str(profile["password"])
    server = str(profile["server"])
    timeout = int(profile.get("timeout", 8000) or 8000)
    portable = bool(profile.get("portable", False))
    terminal_path = str(profile.get("terminal_path", "") or "").strip()

    def _init_then_login(use_credentials_in_initialize: bool = False) -> Tuple[bool, Any]:
        try:
            mt5.shutdown()
            time.sleep(0.35)
        except Exception:
            pass

        init_kwargs: Dict[str, Any] = {"timeout": timeout, "portable": portable}
        if terminal_path:
            init_kwargs["path"] = terminal_path

        if use_credentials_in_initialize:
            init_kwargs.update({
                "login": login,
                "password": password,
                "server": server,
            })

        try:
            ok = mt5.initialize(**init_kwargs)
        except Exception as exc:
            return False, ("exception", str(exc))

        if not ok:
            return False, mt5.last_error()

        # Force the selected Demo/Live account even if MT5 opened an old session.
        try:
            login_ok = mt5.login(login, password=password, server=server, timeout=timeout)
        except Exception as exc:
            return False, ("login_exception", str(exc))

        if not login_ok:
            return False, mt5.last_error()

        return True, None

    # Credentials-first is required for Demo/Live separation.
    # Starting MT5 without credentials can attach to the already-open Live/netting
    # terminal session and make Demo fail or show the wrong account.
    ok, err = _init_then_login(True)

    if not ok:
        _log_mt5_event("connect_retry_without_initialize_credentials", {
            "mode": profile.get("mode"),
            "login": profile.get("login"),
            "server": profile.get("server"),
            "error": err,
        })
        ok, err = _init_then_login(False)

    if not ok:
        try:
            mt5.shutdown()
        except Exception:
            pass
        detail = _mt5_error_detail(err)
        _log_mt5_event("connect_failed_initialize_or_login", {
            "mode": profile.get("mode"),
            "login": profile.get("login"),
            "server": profile.get("server"),
            "error": err,
        })
        return False, f"MT5 connection failed for {login} on {server}: {err}.{detail}", None

    account_info = mt5.account_info()
    if account_info is None:
        err = mt5.last_error()
        mt5.shutdown()
        _log_mt5_event("connect_failed_account_info", {
            "mode": profile.get("mode"),
            "login": profile.get("login"),
            "server": profile.get("server"),
            "error": err,
        })
        return False, f"MT5 account_info failed: {err}", None

    info = account_info._asdict()
    returned_login = str(info.get("login", "")).strip()
    if returned_login != str(login):
        try:
            mt5.login(login, password=password, server=server, timeout=timeout)
            account_info = mt5.account_info()
            info = account_info._asdict() if account_info is not None else {}
            returned_login = str(info.get("login", "")).strip()
        except Exception:
            pass

    if returned_login != str(login):
        got = info.get("login", "unknown")
        mt5.shutdown()
        _log_mt5_event("connect_wrong_account", {
            "mode": profile.get("mode"),
            "requested_login": login,
            "requested_server": server,
            "returned_login": got,
            "returned_server": info.get("server"),
        })
        return False, f"MT5 opened the wrong account. Expected {login}, but terminal is on {got}. Close MT5 and connect again."

    _log_mt5_event("connect_success", {
        "mode": profile.get("mode"),
        "requested_login": profile.get("login"),
        "requested_server": profile.get("server"),
        "returned_login": info.get("login"),
        "returned_server": info.get("server"),
    })
    return True, "MT5 connected successfully.", info


def get_mt5_positions() -> List[Dict[str, Any]]:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []
    positions = mt5.positions_get()
    return [] if positions is None else [p._asdict() for p in positions]


def get_mt5_orders() -> List[Dict[str, Any]]:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []
    orders = mt5.orders_get()
    return [] if orders is None else [o._asdict() for o in orders]


def disconnect_mt5() -> None:
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
    """Verify MT5 returned the same login/server we asked for."""
    if not account_info:
        return False
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
    """
    Sends a market order through MT5 after connecting with the selected Demo/Live profile.
    This function is execution-capable, but Live mode is blocked unless allow_live=True.
    """
    mode = str(profile.get("mode", "Demo")).title()
    if mode == "Live" and not allow_live:
        return {"ok": False, "message": "Live order blocked. Set allow_live=True only after all live risk checks are approved."}

    connected, message, account_info = connect_mt5(profile)
    if not connected:
        return {"ok": False, "message": message, "phase": "connect"}

    try:
        import MetaTrader5 as mt5
    except ImportError:
        shutdown_mt5()
        return {"ok": False, "message": "MetaTrader5 package is not installed."}

    symbol = str(order.get("symbol", "")).strip()
    action = str(order.get("action", order.get("direction", ""))).upper().strip()
    volume = float(order.get("volume", 0) or 0)
    sl = float(order.get("sl", order.get("stop_loss", 0)) or 0)
    tp = float(order.get("tp", order.get("take_profit", 0)) or 0)
    deviation = int(order.get("deviation", 20) or 20)
    magic = int(order.get("magic", 777001) or 777001)
    comment = str(order.get("comment", "TradeSmart Agent"))[:31]

    if not symbol or action not in {"BUY", "SELL"} or volume <= 0:
        shutdown_mt5()
        return {"ok": False, "message": "Invalid order. Required: symbol, BUY/SELL action, volume > 0."}

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
        "type_filling": int(order.get("type_filling", mt5.ORDER_FILLING_IOC)),
    }

    if sl > 0:
        request["sl"] = sl
    if tp > 0:
        request["tp"] = tp

    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        shutdown_mt5()
        return {"ok": False, "message": f"MT5 order_send returned None: {err}", "request": request}

    result_dict = result._asdict()
    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    shutdown_mt5()

    return {
        "ok": ok,
        "message": "Order placed." if ok else f"Order rejected. Retcode: {result.retcode}",
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


def run_tradesmart_agent_cycle(profile: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safe near-execution agent cycle.
    Reads MT5 account, positions, and pending orders, then returns an execution plan.
    It does NOT place orders yet. Add order_send only after your safety layer is approved.
    """
    connected, message, account_info = connect_mt5(profile)
    if not connected:
        return {"ok": False, "message": message, "phase": "connect"}

    positions = get_mt5_positions()
    orders = get_mt5_orders()
    shutdown_mt5()

    max_open_trades = int(rules.get("max_open_trades", 1) or 1)
    can_consider_new_trade = len(positions) < max_open_trades

    return {
        "ok": True,
        "phase": "scan",
        "message": "TradeSmart Agent scanned MT5 and built a safe execution plan. No live order was sent.",
        "account": {
            "login": account_info.get("login"),
            "server": account_info.get("server"),
            "balance": account_info.get("balance"),
            "equity": account_info.get("equity"),
            "currency": account_info.get("currency"),
        },
        "positions_count": len(positions),
        "pending_orders_count": len(orders),
        "can_consider_new_trade": can_consider_new_trade,
        "rules": rules,
        "next_step": "Connect strategy signal validation, spread checks, max-loss guard, and manual/auto execution approval.",
    }
