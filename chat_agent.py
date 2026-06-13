"""
chat_agent.py — @Agent responder wired to production ai_api.py
==============================================================
Place this file in the MAIN project folder next to ai_api.py.
"""
from __future__ import annotations

import re

AGENT_USER = "@Agent"
AGENT_ROLE = "agent"
AGENT_SYSTEM = """You are TradeSmart Agent, an expert AI assistant embedded in a live trading chat room.
You specialise in gold (XAUUSD, GC=F), forex, technical analysis, economic events, and market structure.
Keep replies concise unless a detailed breakdown is clearly needed.
Use plain text with direct, practical wording.
Never make up live prices, news, account data, or market data. If you are unsure, say so honestly.
Address the user by name when it is provided."""


def _strip_mention(text: str) -> str:
    return re.sub(r"@[Aa]gent\b", "", text or "").strip()


def call_agent(user_name: str, raw_message: str) -> str:
    question = _strip_mention(raw_message)
    if not question:
        question = "Hello"

    prompt = f"{user_name} asks: {question}"
    try:
        from ai_api import call_best_ai
        provider, reply_text = call_best_ai(AGENT_SYSTEM, prompt, max_tokens=512)
        reply_text = reply_text.strip() or "Sorry, I did not receive a response."
        return f"@{user_name} — {reply_text}"
    except Exception as exc:
        return f"@{user_name} — Agent is not available yet. {exc}"


def get_agent_status() -> str:
    try:
        from ai_api import configured_provider_summary
        return configured_provider_summary()
    except Exception as exc:
        return f"not connected: {exc}"
