"""
ai_api.py — production multi-provider AI router for Dropz Universal Agent
=======================================================================
Place this file in the MAIN project folder next to app.py / streamlit_app.py.

Checks these locations safely:
  1. ai_api.local.json in project root
  2. .env in project root / current working folder / parent folders
  3. Streamlit secrets
  4. OS environment variables

Never commit real API keys.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class AIProvider:
    name: str
    key_name: str
    model_name: str
    default_model: str
    enabled_name: str


PROVIDERS: list[AIProvider] = [
    # OpenAI first by default because it is usually the most reliable fallback for this app.
    # You can change AI_PROVIDER_ORDER in .env / Streamlit secrets / ai_api.local.json.
    AIProvider("openai", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-4o-mini", "OPENAI_ENABLED"),
    AIProvider("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-sonnet-4-5", "ANTHROPIC_ENABLED"),
    AIProvider("gemini", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-1.5-flash", "GEMINI_ENABLED"),
]

ROOT = Path(__file__).resolve().parent
_DOTENV_LOADED = False
_JSON_CACHE: dict[str, str] | None = None
_SECRET_SOURCE_CACHE: dict[str, str] = {}


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for p in [ROOT, Path.cwd(), ROOT.parent, Path.cwd().parent]:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in roots:
            roots.append(rp)
    return roots


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        text = text[1:-1].strip()
    return text


def _flatten_json(data: dict[str, Any]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            provider = str(key).upper()
            aliases = {
                "API_KEY": f"{provider}_API_KEY",
                "KEY": f"{provider}_API_KEY",
                "MODEL": f"{provider}_MODEL",
                "ENABLED": f"{provider}_ENABLED",
            }
            for child_key, child_value in value.items():
                child = str(child_key).upper()
                env_key = aliases.get(child, f"{provider}_{child}")
                cleaned = _clean_value(child_value)
                if cleaned:
                    flat[env_key] = cleaned
        else:
            cleaned = _clean_value(value)
            if cleaned:
                flat[str(key).upper()] = cleaned
    return flat


def _read_local_json() -> dict[str, str]:
    global _JSON_CACHE
    if _JSON_CACHE is not None:
        return _JSON_CACHE
    _JSON_CACHE = {}
    for root in _candidate_roots():
        path = root / "ai_api.local.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _JSON_CACHE.update(_flatten_json(raw))
        except Exception:
            continue
    return _JSON_CACHE


def _load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    env_paths = []
    for root in _candidate_roots():
        p = root / ".env"
        if p.exists() and p not in env_paths:
            env_paths.append(p)

    try:
        from dotenv import load_dotenv  # type: ignore
        for env_path in env_paths:
            load_dotenv(env_path, override=False)
    except Exception:
        # Manual fallback if python-dotenv is not installed.
        for env_path in env_paths:
            try:
                for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = _clean_value(v)
                    if k and v and not os.environ.get(k):
                        os.environ[k] = v
            except Exception:
                continue


def _get_streamlit_secret(name: str) -> str:
    try:
        import streamlit as st  # type: ignore
        value = st.secrets.get(name, "")
        return _clean_value(value)
    except Exception:
        return ""


def get_secret(name: str, default: str = "") -> str:
    """Return a secret/config value. Values are never printed or exposed."""
    key = name.upper().strip()

    value = _read_local_json().get(key, "")
    if value:
        _SECRET_SOURCE_CACHE[key] = "ai_api.local.json"
        return value

    _load_dotenv_once()
    value = _clean_value(os.environ.get(key, ""))
    if value:
        _SECRET_SOURCE_CACHE[key] = ".env / environment"
        return value

    value = _get_streamlit_secret(key)
    if value:
        _SECRET_SOURCE_CACHE[key] = "Streamlit secrets"
        return value

    value = _clean_value(os.environ.get(key, ""))
    if value:
        _SECRET_SOURCE_CACHE[key] = "environment"
        return value

    return default


def get_secret_source(name: str) -> str:
    key = name.upper().strip()
    if key not in _SECRET_SOURCE_CACHE:
        get_secret(key)
    return _SECRET_SOURCE_CACHE.get(key, "not found")


def _truthy(value: str, default: bool = True) -> bool:
    cleaned = _clean_value(value)
    if not cleaned:
        return default
    return cleaned.lower() not in {"0", "false", "no", "off", "disabled"}


def _provider_enabled(provider: AIProvider) -> bool:
    return _truthy(get_secret(provider.enabled_name, "true"), default=True)


def _model(provider: AIProvider) -> str:
    return get_secret(provider.model_name, provider.default_model)


def _provider_order() -> list[str]:
    raw = get_secret("AI_PROVIDER_ORDER", "openai,anthropic,gemini")
    names = [x.strip().lower() for x in raw.split(",") if x.strip()]
    known = {p.name for p in PROVIDERS}
    ordered = [name for name in names if name in known]
    for p in PROVIDERS:
        if p.name not in ordered:
            ordered.append(p.name)
    return ordered


def available_providers() -> list[AIProvider]:
    provider_map = {p.name: p for p in PROVIDERS}
    ready: list[AIProvider] = []
    for name in _provider_order():
        provider = provider_map.get(name)
        if provider and _provider_enabled(provider) and get_secret(provider.key_name):
            ready.append(provider)
    return ready


def configured_provider_summary() -> str:
    ready = []
    for provider in available_providers():
        ready.append(f"{provider.name} via {get_secret_source(provider.key_name)}")
    return ", ".join(ready) if ready else "none"


def diagnose_ai_config() -> dict[str, dict[str, str | bool]]:
    """Safe diagnostics for a CEO/admin UI. Does not reveal keys."""
    out: dict[str, dict[str, str | bool]] = {}
    for provider in PROVIDERS:
        key = get_secret(provider.key_name)
        out[provider.name] = {
            "enabled": _provider_enabled(provider),
            "has_key": bool(key),
            "source": get_secret_source(provider.key_name),
            "model": _model(provider),
        }
    return out


def _call_anthropic(api_key: str, model: str, system: str, prompt: str, max_tokens: int) -> str:
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install missing package: pip install anthropic") from exc

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip() if response.content else ""


def _call_openai(api_key: str, model: str, system: str, prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install missing package: pip install openai") from exc

    client = OpenAI(api_key=api_key)

    # Newer OpenAI accounts support chat.completions reliably for gpt-4o-mini.
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _call_gemini(api_key: str, model: str, system: str, prompt: str, max_tokens: int) -> str:
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install missing package: pip install google-generativeai") from exc

    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model_name=model, system_instruction=system)
    response = client.generate_content(prompt, generation_config={"max_output_tokens": max_tokens})
    return (getattr(response, "text", "") or "").strip()


CALLERS: dict[str, Callable[[str, str, str, str, int], str]] = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
}


def _safe_error_text(exc: Exception) -> str:
    text = str(exc)
    # Keep enough detail for debugging but do not dump giant SDK objects into chat.
    text = " ".join(text.split())
    if len(text) > 420:
        text = text[:420] + "..."
    return text


def call_best_ai(system: str, prompt: str, max_tokens: int = 512) -> tuple[str, str]:
    providers = available_providers()
    if not providers:
        expected = ", ".join(provider.key_name for provider in PROVIDERS)
        roots = ", ".join(str(p) for p in _candidate_roots())
        raise RuntimeError(f"No AI API keys configured. Add one of: {expected}. Checked roots: {roots}")

    errors: list[str] = []
    tried: list[str] = []
    for provider in providers:
        caller = CALLERS.get(provider.name)
        if caller is None:
            continue
        tried.append(provider.name)
        try:
            reply = caller(get_secret(provider.key_name), _model(provider), system, prompt, max_tokens).strip()
            if reply:
                return provider.name, reply
            errors.append(f"{provider.name}: empty response")
        except Exception as exc:
            errors.append(f"{provider.name}: {_safe_error_text(exc)}")
            # Do not stop on billing/rate/package/model errors. Continue to the next configured provider.
            continue

    configured = configured_provider_summary()
    raise RuntimeError("All configured AI providers failed. Tried: " + ", ".join(tried) + ". Configured: " + configured + ". " + " | ".join(errors))
