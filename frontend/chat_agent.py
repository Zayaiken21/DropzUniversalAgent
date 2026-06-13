"""
chat_agent.py — @Agent AI responder for TradeSmart chat
=========================================================
When a user sends a message containing @Agent, this module:
  1. Strips the @Agent mention from the question
  2. Sends it to the Anthropic API with a gold-trading system prompt
  3. Posts the reply back into the chat as user "@Agent" with role "agent"

The agent is called synchronously inside the Streamlit refresh cycle so no
separate process or websocket is needed.

Requirements: pip install anthropic
"""
from __future__ import annotations

import re
import os

AGENT_USER    = "@Agent"
AGENT_ROLE    = "agent"
AGENT_SYSTEM  = """You are TradeSmart Agent, an expert AI assistant embedded in a live trading chat room.
You specialise in gold (XAUUSD, GC=F), forex, technical analysis, economic events, and market structure.
Keep replies concise (3–6 sentences max) unless a detailed breakdown is clearly needed.
Use plain text — no markdown headers, no bullet lists — just clear, direct sentences.
Never make up prices or data. If you are unsure, say so honestly.
Address the user by name when it is provided."""

try:
    import anthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False


def _strip_mention(text: str) -> str:
    """Remove @Agent / @agent from the message and strip whitespace."""
    return re.sub(r"@[Aa]gent\b", "", text).strip()


def _get_client() -> "anthropic.Anthropic | None":
    if not _ANTHROPIC_OK:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def call_agent(user_name: str, raw_message: str) -> str:
    """
    Call the Anthropic API and return the agent's reply text.
    Returns an error string if the API is unavailable.
    """
    question = _strip_mention(raw_message)
    if not question:
        question = "Hello"

    client = _get_client()
    if client is None:
        if not _ANTHROPIC_OK:
            return (
                "@" + user_name + " — I'm not available yet. "
                "Ask an admin to run: pip install anthropic "
                "and set the ANTHROPIC_API_KEY environment variable."
            )
        return (
            "@" + user_name + " — ANTHROPIC_API_KEY is not set. "
            "Please add it to your environment variables."
        )

    prompt = f"{user_name} asks: {question}"
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=AGENT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        reply_text = response.content[0].text.strip() if response.content else "Sorry, I had no response."
        return f"@{user_name} — {reply_text}"
    except Exception as exc:
        return f"@{user_name} — Agent error: {exc}"
