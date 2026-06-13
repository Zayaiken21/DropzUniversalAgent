
from __future__ import annotations

import html
import re
import sqlite3
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

PAGE_CONFIG = {
    "name": "Education",
    "icon": "🎓",
    "roles": ["ceo", "client", "admin", "trader"],
}

DB_PATH = Path("data/education_center.db")
STYLE_PATH = Path("styles/education.css")
DEFAULT_TZ = "America/New_York"

DEFAULT_SETTINGS = {
    "announcement": "Risk first. Structure, liquidity, timing, confirmation, and review must agree before execution.",
    "zoom_room_name": "Dropz Live Trading Classroom",
    "zoom_room_url": "https://zoom.us/",
    "zoom_room_note": "Use this room for live classes, chart breakdowns, Q&A, replays, and weekly planning.",
}

COURSE_LIBRARY: list[dict[str, Any]] = [
    {
        "id": "starter-map",
        "track": "Foundation",
        "title": "The Trader Roadmap: From Beginner to Consistent Operator",
        "level": "Beginner",
        "time": "35 min",
        "outcome": "Understand the full workflow from chart reading to execution review.",
        "overview": "Trading is not one indicator or one entry trick. A complete trader learns market context, liquidity, risk control, execution timing, psychology, journaling, and review. This module gives users the map so every other lesson has a purpose.",
        "deep_dive": [
            ("The five-part workflow", "1) Context: what market are we in? 2) Location: where is liquidity or value? 3) Trigger: what confirms the idea? 4) Risk: where is invalidation? 5) Review: what did we learn?"),
            ("Why beginners struggle", "Most new traders jump from signal to signal. They enter because price moved, not because a repeatable setup appeared. The goal is to build a process that can be checked before and after every trade."),
            ("What consistency means", "Consistency is not winning every trade. It means taking the same quality of decision repeatedly, with controlled risk, then reviewing enough trades to see if the edge is real."),
            ("Professional standard", "A trade idea should be explainable in one sentence: 'I am trading [direction] because [structure/liquidity] during [session], entering after [confirmation], risking [amount], targeting [liquidity/value].'"),
        ],
        "process": ["Check higher timeframe bias", "Mark key liquidity and value areas", "Wait for session timing", "Use confirmation trigger", "Journal decision quality"],
        "mistakes": ["Starting with lot size", "Copying signals without context", "Changing strategy after every loss", "Trading without a daily stop"],
        "drill": "Write your one-sentence trade plan template and use it before every trade for one week.",
    },
    {
        "id": "market-structure-masterclass",
        "track": "Foundation",
        "title": "Market Structure Masterclass: Trend, Range, BOS, CHoCH",
        "level": "Beginner → Intermediate",
        "time": "55 min",
        "outcome": "Read direction and know when price is trending, ranging, continuing, or potentially reversing.",
        "overview": "Market structure is the backbone of technical trading. It tells you whether buyers or sellers are in control and prevents random entries inside noise.",
        "deep_dive": [
            ("Swing highs and lows", "A valid swing high/low should stand out compared to nearby candles. Use it to frame structure, not every tiny wick. On higher timeframes, swings carry more weight."),
            ("Trend structure", "Bullish structure prints higher highs and higher lows. Bearish structure prints lower lows and lower highs. A trend is not broken by one small wick; look for meaningful displacement and candle closes."),
            ("BOS", "A break of structure supports continuation when price breaks the previous important swing in the trend direction. BOS is stronger when followed by acceptance and pullback support/resistance."),
            ("CHoCH", "Change of character is an early warning that short-term order flow may be shifting. It is not automatic reversal; it needs context, liquidity, and follow-through."),
            ("Range structure", "Ranges create equal highs/lows and internal liquidity. Good traders do not force trend trades inside ranges; they wait for sweep, breakout, or edge-to-edge logic."),
        ],
        "process": ["Mark 1H and 15M major highs/lows", "Label trend or range", "Wait for meaningful close through structure", "Retest or sweep must confirm", "Avoid mid-range entries"],
        "mistakes": ["Calling every wick BOS", "Ignoring higher timeframe", "Trading the middle of a range", "Entering before close confirmation"],
        "drill": "Open XAUUSD 15M and label the last three BOS/CHoCH events. Decide which were real and which were noise.",
    },
    {
        "id": "risk-management",
        "track": "Foundation",
        "title": "Risk Management: Position Sizing, Daily Loss, Drawdown Control",
        "level": "Beginner → Advanced",
        "time": "60 min",
        "outcome": "Know exactly how much can be lost before every trade and protect the account from bad days.",
        "overview": "Risk management is what allows a trader to survive long enough for skill to compound. Every strategy has losing streaks; risk keeps those streaks from becoming account damage.",
        "deep_dive": [
            ("Risk per trade", "Many developing traders should risk 0.25%–1% per trade. The goal is to learn without making one mistake too expensive."),
            ("Daily max loss", "Set a daily lockout rule. Example: stop after -2R, two emotional trades, or a fixed percentage loss. This prevents revenge trading."),
            ("Lot size formula", "Risk dollars divided by stop distance and tick value = lot size. Lot size should never be chosen because the setup 'feels strong'."),
            ("Risk/reward reality", "A 1:3 trade is only useful if the target is realistic. The target should be liquidity, value area edge, previous high/low, or measured move."),
            ("Drawdown psychology", "A trader in drawdown must reduce size, reduce frequency, and review execution errors before trying to recover aggressively."),
        ],
        "process": ["Choose risk percentage", "Find invalidation", "Calculate lot size", "Set daily stop", "Log R multiple"],
        "mistakes": ["Moving stop loss", "Doubling after losses", "Taking more trades to recover", "Risking more on live than demo"],
        "drill": "Use a $10,000 sample account. Calculate risk for 0.5%, a 50-point stop, and a $1/point contract value.",
    },
    {
        "id": "timeframes",
        "track": "Execution",
        "title": "Timeframe Alignment: Monthly to 1-Minute Scalping Map",
        "level": "Intermediate",
        "time": "70 min",
        "outcome": "Use each timeframe for its job without mixing signals or overloading the chart.",
        "overview": "Every timeframe has a purpose. Higher timeframes define context, middle timeframes define setup, and lower timeframes refine entries. The mistake is treating a 1M candle like it can override the 1H map.",
        "deep_dive": [
            ("Monthly/Weekly", "Used for macro levels, long-term highs/lows, major supply/demand, and trend environment. Day traders do not need to stare at it all day, but should know where price is relative to major levels."),
            ("Daily/4H", "Best for identifying major directional bias, previous day/week levels, premium/discount, and high-impact areas. Gold and indices often react strongly at these zones."),
            ("1H/30M", "Used for session map, intraday structure, major liquidity pools, and where the day may expand or reverse."),
            ("15M/5M", "Best for setup confirmation: sweep, displacement, BOS/CHoCH, FVG, order block, and session range behavior. For scalping, 5M often decides if the idea is clean."),
            ("1M", "Entry refinement only. It can help reduce stop size, but it also creates noise. Use it after higher-timeframe context is already aligned."),
            ("Top-down routine", "Start high, move low: HTF bias → session level → setup timeframe → trigger timeframe → execution rule. Do not reverse this process."),
        ],
        "process": ["Mark 1D/4H levels", "Use 1H for session structure", "Use 15M/5M for setup", "Use 1M only for entry trigger", "Invalidation must match setup timeframe"],
        "mistakes": ["Letting 1M noise cancel 1H bias", "Using too many timeframes at once", "Entering on 1M without 5M context", "Ignoring previous day high/low"],
        "drill": "Pick one XAUUSD move and write what each timeframe was telling you: 1H, 15M, 5M, 1M.",
    },
    {
        "id": "liquidity-smc",
        "track": "Smart Money",
        "title": "Liquidity, Sweeps, Stops, and Displacement",
        "level": "Intermediate",
        "time": "75 min",
        "outcome": "Recognize where liquidity sits and wait for confirmation after it is taken.",
        "overview": "Liquidity is where orders are likely resting. Retail stop losses, breakout orders, previous highs/lows, equal highs/lows, and session extremes can all become targets before price reveals direction.",
        "deep_dive": [
            ("Buy-side liquidity", "Sits above obvious highs. Price may run above the highs to fill orders, then reject if the move was a stop hunt."),
            ("Sell-side liquidity", "Sits below obvious lows. A sweep below lows followed by strong bullish displacement can signal a reversal opportunity."),
            ("Session liquidity", "Asia high/low, London high/low, previous day high/low, and NY morning extremes are important for XAUUSD and indices."),
            ("Displacement", "A strong impulsive candle or series of candles showing urgency. After a sweep, displacement away from the level is confirmation that the sweep may matter."),
            ("Continuation vs reversal", "Not every sweep reverses. If price sweeps and accepts beyond the level, it may be breakout continuation. Context decides."),
        ],
        "process": ["Mark equal highs/lows", "Mark previous day/session extremes", "Wait for sweep", "Require displacement", "Enter on retrace only if risk is clean"],
        "mistakes": ["Selling every high wick", "Buying every low wick", "Ignoring candle close", "Forcing reversal against strong trend"],
        "drill": "Screenshot three liquidity sweeps and label whether each was reversal, continuation, or fake signal.",
    },
    {
        "id": "fvg-ob",
        "track": "Smart Money",
        "title": "FVGs, Order Blocks, Breakers, and Mitigation",
        "level": "Intermediate → Advanced",
        "time": "80 min",
        "outcome": "Use imbalance and institutional-style zones with context instead of blindly entering every marked area.",
        "overview": "FVGs and order blocks are useful only when they are tied to displacement, structure, liquidity, and session timing. They are zones for decision-making, not automatic entries.",
        "deep_dive": [
            ("Fair Value Gap", "A three-candle imbalance where price moved so fast that a gap between candle one and candle three remains. Quality improves after sweep and displacement."),
            ("Order Block", "A prior candle/zone before displacement. It can act as a reaction area if it caused a meaningful move and aligns with structure."),
            ("Breaker", "A failed order block can become a breaker when price invalidates it, then retests from the other side."),
            ("Mitigation", "Price returning to rebalance/mitigate an inefficient move. Not every zone needs full fill; partial fill can be enough on strong trend days."),
            ("Zone selection", "Choose the cleanest zone that caused displacement and sits at good location. Too many zones create hesitation."),
        ],
        "process": ["Identify sweep/BOS", "Mark displacement candle", "Draw FVG/OB", "Filter by session and HTF bias", "Wait for confirmation inside zone"],
        "mistakes": ["Marking every tiny imbalance", "Entering zones without confirmation", "Stacking too many boxes", "Ignoring invalidation"],
        "drill": "Mark the top two FVGs and top two OBs from today. Explain which one you would actually trade and why.",
    },
    {
        "id": "volume-profile",
        "track": "Market Profile",
        "title": "Volume Profile: POC, VAH, VAL, HVN, LVN",
        "level": "Intermediate → Advanced",
        "time": "90 min",
        "outcome": "Understand where volume traded, where price accepted value, and where reactions may happen.",
        "overview": "Volume Profile shows volume by price instead of by time. It helps traders identify accepted value, high-volume magnets, low-volume rejection zones, and key levels like POC, VAH, and VAL.",
        "deep_dive": [
            ("POC", "Point of Control is the price with the highest traded volume in the selected range/session. It often acts like a magnet or decision level."),
            ("VAH/VAL", "Value Area High and Value Area Low usually frame the area where around 70% of volume traded. Above VAH can show bullish acceptance; below VAL can show bearish acceptance."),
            ("HVN", "High Volume Node shows acceptance and balance. Price may slow, rotate, or get attracted back to HVNs."),
            ("LVN", "Low Volume Node shows rejection/inefficiency. Price may move quickly through LVNs or reject from them."),
            ("Session profile", "For intraday trading, use the correct session/range. A random profile over too much data can give levels that do not match today’s auction."),
            ("Combining with SMC", "A liquidity sweep into VAH/VAL with displacement away can be stronger than a sweep alone. POC can be a target, magnet, or chop zone depending on context."),
        ],
        "process": ["Choose correct session/range", "Mark POC/VAH/VAL", "Note HVN/LVN", "Watch acceptance vs rejection", "Combine with structure/liquidity"],
        "mistakes": ["Using random profile range", "Treating POC as automatic entry", "Ignoring current session", "Trading inside value with no edge"],
        "drill": "Draw yesterday’s profile on XAUUSD. Mark POC, VAH, VAL, then write where today accepted or rejected value.",
    },
    {
        "id": "sessions-news",
        "track": "Execution",
        "title": "Sessions, News, and XAUUSD Volatility Windows",
        "level": "Intermediate",
        "time": "65 min",
        "outcome": "Trade the times where your setups have enough liquidity and avoid dangerous news traps.",
        "overview": "Gold, indices, and USD pairs respond strongly to session transitions and economic releases. Timing can make the difference between clean displacement and random chop.",
        "deep_dive": [
            ("Asia", "Often builds liquidity ranges. Good for marking highs/lows, not always ideal for aggressive breakout trading."),
            ("London", "Can create early expansion, fakeouts, and sweeps of Asia liquidity. Watch 2:00–5:00 AM New York depending on market."),
            ("New York", "Gold reacts heavily to USD news, yields, and the equity open. 8:30 AM news and 9:30 AM stock open can create fast moves."),
            ("London/NY overlap", "Often best liquidity but also high volatility. Use confirmation and avoid chasing the first spike."),
            ("News rules", "Before CPI, NFP, FOMC, PPI, unemployment, and rate decisions, spreads and slippage can expand. Decide ahead if you trade news or wait after reaction."),
        ],
        "process": ["Check economic calendar", "Mark Asia range", "Watch London sweep/expansion", "Wait after NY news spike", "Trade only confirmed post-news structure"],
        "mistakes": ["Trading into news blindly", "Forcing trades during dead zones", "Ignoring spread/slippage", "Revenge trading after news spike"],
        "drill": "Pick the next high-impact USD news event and write your no-trade window before and after it.",
    },
    {
        "id": "entries-exits",
        "track": "Execution",
        "title": "Entries, Stops, Targets, Partials, and Trade Management",
        "level": "Intermediate → Advanced",
        "time": "85 min",
        "outcome": "Enter only after confirmation and manage the trade based on rules instead of emotion.",
        "overview": "A good idea can be ruined by bad execution. This module turns setup logic into exact entry, stop, target, and management decisions.",
        "deep_dive": [
            ("Entry trigger", "Examples: close through micro structure, displacement away from zone, retest reaction, or confirmed rejection candle. Pick triggers you can repeat."),
            ("Stop placement", "Stop should sit where your idea is wrong: beyond sweep, beyond structure, beyond OB/FVG invalidation. Avoid random tight stops inside noise."),
            ("Targets", "Use liquidity, POC, VAH/VAL, previous highs/lows, session extremes, measured moves, or 1:2/1:3 only when realistic."),
            ("Partials", "Taking partial profit can reduce emotion but should be rule-based. Example: partial at 1R or first liquidity, move stop only after structure supports it."),
            ("Trade management", "Before entry, decide what happens at +1R, -0.5R, sweep failure, news, and time-based invalidation."),
        ],
        "process": ["Define trigger", "Define invalidation", "Calculate lot size", "Place target at real liquidity/value", "Manage with prewritten rules"],
        "mistakes": ["Entering because price touched a line", "Moving target farther", "Moving stop wider", "Closing early from fear without rule"],
        "drill": "Write an entry checklist with 5 yes/no rules. No trade unless all are yes.",
    },
    {
        "id": "psychology-discipline",
        "track": "Mindset",
        "title": "Psychology: Discipline, Patience, Revenge Trading, Confidence",
        "level": "All levels",
        "time": "70 min",
        "outcome": "Build rules that protect decision quality when candles move fast.",
        "overview": "Psychology is not motivational quotes. It is designing rules and habits that prevent emotional decisions under pressure.",
        "deep_dive": [
            ("Revenge trading", "Usually starts after a loss when the trader feels the need to immediately recover. The solution is a mandatory pause and daily loss rule."),
            ("FOMO", "Fear of missing out makes traders chase after the entry window is gone. A missed trade is not a loss; chasing can create one."),
            ("Overconfidence", "After wins, traders often increase size or relax rules. A green day with bad rules is still a warning sign."),
            ("Patience", "Professional patience means waiting for your exact conditions, not sitting at the screen hoping something appears."),
            ("Confidence", "Real confidence comes from logged evidence: screenshots, setups, win rate by setup, average R, and mistake reduction."),
        ],
        "process": ["Write session plan", "Set emotional stop rule", "Pause after loss", "Review behavior score", "Reduce size after rule breaks"],
        "mistakes": ["Trading angry", "Chasing candles", "Hiding mistakes", "Increasing size to feel confident"],
        "drill": "Create a personal rule: after one emotional mistake, what exact action do you take?",
    },
    {
        "id": "journal-review",
        "track": "Review",
        "title": "Trade Log Review: Data, Screenshots, Metrics, Weekly Improvement",
        "level": "All levels",
        "time": "60 min",
        "outcome": "Turn every session into a measurable improvement loop.",
        "overview": "The trade log is where random trading becomes a business process. It helps you find which setups work, which times hurt you, and which mistakes repeat.",
        "deep_dive": [
            ("What to log", "Date, session, symbol, setup, direction, entry, stop, target, exit, R multiple, reason, mood, mistake, and screenshot."),
            ("Valid loss vs bad loss", "A valid loss followed the plan. A bad loss broke rules. Treat them differently during review."),
            ("Setup statistics", "After 20+ similar trades, compare win rate, average R, time of day, and mistake frequency by setup."),
            ("Weekly review", "Choose one rule to keep, one to remove, one to improve. Do not rebuild the whole system every week."),
            ("CEO/client education use", "The CEO can use Zoom classes and videos to teach users what the data says about the week’s market behavior."),
        ],
        "process": ["Log every trade", "Tag mistakes", "Screenshot before/after", "Review weekly", "Adjust one rule"],
        "mistakes": ["Only reviewing losses", "Deleting losing trades", "Changing strategy daily", "Not measuring by setup"],
        "drill": "Review your last 10 trades and find your most expensive repeated mistake.",
    },
]

QUIZ_BANK: list[dict[str, Any]] = [
    {"id":"q1","track":"Foundation","question":"What should come before planning a trade entry?","options":["Lot size", "Market context, structure, and risk", "A social media signal", "A random candle color"],"answer":"Market context, structure, and risk","explain":"Context and risk define whether an entry is worth considering. Lot size comes after invalidation is known."},
    {"id":"q2","track":"Foundation","question":"What does a valid stop loss represent?","options":["A random tight number", "Where the trade idea is invalid", "A place to move farther away", "The exact target"],"answer":"Where the trade idea is invalid","explain":"A stop should be placed where your setup is wrong, such as beyond structure or the sweep extreme."},
    {"id":"q3","track":"Execution","question":"What is the best use of the 1-minute timeframe for scalping?","options":["Replace all higher timeframe context", "Entry refinement after bias is already clear", "Predict the whole week", "Ignore risk"],"answer":"Entry refinement after bias is already clear","explain":"The 1M is noisy. Use it only after higher timeframe and setup timeframe context is aligned."},
    {"id":"q4","track":"Smart Money","question":"A liquidity sweep becomes more meaningful when followed by what?","options":["Immediate revenge entry", "Displacement away from the swept level", "Doubling the lot", "Ignoring the session"],"answer":"Displacement away from the swept level","explain":"Displacement shows urgency away from the swept liquidity and helps confirm that the sweep may matter."},
    {"id":"q5","track":"Smart Money","question":"What makes a fair value gap higher quality?","options":["It appears randomly in chop", "It appears after displacement with structure/session context", "It is the smallest candle", "It has no invalidation"],"answer":"It appears after displacement with structure/session context","explain":"FVGs are best used after meaningful displacement and aligned context. Not every gap is tradeable."},
    {"id":"q6","track":"Market Profile","question":"What does POC mean in Volume Profile?","options":["Price of candle", "Point of Control: highest volume price in selected range", "Profit-only candle", "Previous open close"],"answer":"Point of Control: highest volume price in selected range","explain":"POC is the price level with the highest traded volume in the chosen profile range/session."},
    {"id":"q7","track":"Market Profile","question":"What do VAH and VAL usually frame?","options":["The value area high and low", "The broker spread", "Only candle wicks", "The news calendar"],"answer":"The value area high and low","explain":"VAH and VAL frame the value area where most volume traded, often used to judge acceptance or rejection."},
    {"id":"q8","track":"Execution","question":"Why should traders be careful near major USD news when trading XAUUSD?","options":["Gold never moves on news", "Spreads, slippage, and volatility can expand", "News removes risk", "Stops no longer matter"],"answer":"Spreads, slippage, and volatility can expand","explain":"High-impact USD events can move gold violently. Plan no-trade windows or wait for post-news structure."},
    {"id":"q9","track":"Mindset","question":"What is the best response after an emotional rule-breaking trade?","options":["Immediately double risk", "Pause, log it, and reduce/stop trading according to rules", "Delete the trade", "Blame the broker"],"answer":"Pause, log it, and reduce/stop trading according to rules","explain":"A rule break is a process warning. The correct response is to pause and protect decision quality."},
    {"id":"q10","track":"Review","question":"What is the difference between a valid loss and a bad loss?","options":["A valid loss followed the plan; a bad loss broke rules", "A valid loss is always green", "A bad loss only happens on demo", "There is no difference"],"answer":"A valid loss followed the plan; a bad loss broke rules","explain":"Valid losses are part of trading. Bad losses show behavior/process errors that need correction."},
]

DEFAULT_VIDEOS = [
    {"title":"Start Here: Risk First Trading Plan", "url":"https://www.youtube.com/", "channel":"Dropz Education", "track":"Foundation", "description":"Use this slot for your intro class or public YouTube channel video.", "featured": 1},
]

# ───────────────────────────── database / persistence ─────────────────────────────

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    """Return existing SQLite column names for a table.

    This is intentionally small and local to this page so old local databases,
    Streamlit Cloud databases, and copied client databases can all migrate
    without needing manual resets.
    """
    try:
        rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}
    except Exception:
        return set()


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _rebuild_education_settings_if_needed(con: sqlite3.Connection) -> None:
    """Repair old education_settings schemas that do not have key/value columns.

    The previous build expected education_settings.key to exist. If a user's
    local DB already had a different education_settings table, SQLite kept the
    old table and the page crashed on INSERT. This safely preserves any useful
    settings it can find, moves the bad table aside, and creates the correct
    global settings table used by CEO/client rendering.
    """
    if not _table_exists(con, "education_settings"):
        con.execute("""
            CREATE TABLE education_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        return

    cols = _table_columns(con, "education_settings")
    if {"key", "value", "updated_at"}.issubset(cols):
        return

    now = datetime.now(timezone.utc).isoformat()
    backup_name = f"education_settings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    salvage: list[tuple[str, str, str]] = []

    key_candidates = [c for c in ("key", "setting_key", "name", "setting", "id") if c in cols]
    value_candidates = [c for c in ("value", "setting_value", "content", "data") if c in cols]
    updated_candidates = [c for c in ("updated_at", "created_at", "timestamp") if c in cols]

    if key_candidates and value_candidates:
        key_col = key_candidates[0]
        value_col = value_candidates[0]
        updated_col = updated_candidates[0] if updated_candidates else None
        try:
            select_updated = f", {updated_col}" if updated_col else ""
            rows = con.execute(f"SELECT {key_col}, {value_col}{select_updated} FROM education_settings").fetchall()
            for row in rows:
                k = str(row[0] or "").strip()
                v = str(row[1] or "")
                u = str(row[2] or now) if updated_col and len(row) > 2 else now
                if k:
                    salvage.append((k, v, u))
        except Exception:
            salvage = []

    con.execute(f"ALTER TABLE education_settings RENAME TO {backup_name}")
    con.execute("""
        CREATE TABLE education_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    for k, v, u in salvage:
        con.execute(
            "INSERT OR REPLACE INTO education_settings(key, value, updated_at) VALUES(?,?,?)",
            (k, v, u),
        )


def _ensure_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _init_db() -> None:
    with _connect() as con:
        _rebuild_education_settings_if_needed(con)

        con.execute("""
            CREATE TABLE IF NOT EXISTS zoom_classes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'America/New_York',
                zoom_url TEXT NOT NULL,
                room_name TEXT,
                description TEXT,
                level TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        for column, definition in {
            "title": "TEXT NOT NULL DEFAULT 'Live Zoom Class'",
            "start_at": "TEXT NOT NULL DEFAULT ''",
            "end_at": "TEXT NOT NULL DEFAULT ''",
            "timezone": "TEXT NOT NULL DEFAULT 'America/New_York'",
            "zoom_url": "TEXT NOT NULL DEFAULT ''",
            "room_name": "TEXT",
            "description": "TEXT",
            "level": "TEXT",
            "created_by": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(con, "zoom_classes", column, definition)

        con.execute("""
            CREATE TABLE IF NOT EXISTS education_videos (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                channel TEXT,
                track TEXT,
                description TEXT,
                featured INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        for column, definition in {
            "title": "TEXT NOT NULL DEFAULT 'Trading Video'",
            "url": "TEXT NOT NULL DEFAULT ''",
            "channel": "TEXT",
            "track": "TEXT",
            "description": "TEXT",
            "featured": "INTEGER DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(con, "education_videos", column, definition)

        con.execute("""
            CREATE TABLE IF NOT EXISTS custom_courses (
                id TEXT PRIMARY KEY,
                track TEXT NOT NULL,
                title TEXT NOT NULL,
                level TEXT,
                time TEXT,
                outcome TEXT,
                overview TEXT,
                deep_dive TEXT,
                process TEXT,
                mistakes TEXT,
                drill TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        for column, definition in {
            "track": "TEXT NOT NULL DEFAULT 'Custom'",
            "title": "TEXT NOT NULL DEFAULT 'Custom Lesson'",
            "level": "TEXT",
            "time": "TEXT",
            "outcome": "TEXT",
            "overview": "TEXT",
            "deep_dive": "TEXT",
            "process": "TEXT",
            "mistakes": "TEXT",
            "drill": "TEXT",
            "is_active": "INTEGER DEFAULT 1",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(con, "custom_courses", column, definition)

        con.execute("""
            CREATE TABLE IF NOT EXISTS cleanup_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        if "value" not in _table_columns(con, "cleanup_state"):
            # Rare old/bad schema fallback. This table only stores cleanup metadata,
            # so rebuilding it is safe and avoids future startup crashes.
            backup_name = f"cleanup_state_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            con.execute(f"ALTER TABLE cleanup_state RENAME TO {backup_name}")
            con.execute("""
                CREATE TABLE cleanup_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

        now = datetime.now(timezone.utc).isoformat()
        for key, value in DEFAULT_SETTINGS.items():
            con.execute("""
                INSERT OR IGNORE INTO education_settings(key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, now))

        count = con.execute("SELECT COUNT(*) FROM education_videos").fetchone()[0]
        if count == 0:
            for item in DEFAULT_VIDEOS:
                _insert_video(con, item, commit=False)
        con.commit()
    _weekly_zoom_cleanup()


def _setting(key: str, default: str = "") -> str:
    with _connect() as con:
        row = con.execute("SELECT value FROM education_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _save_setting(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute("""
            INSERT INTO education_settings(key, value, updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, value, now))
        con.commit()


def _safe_role(role: str | None = None) -> str:
    role = str(role or (st.session_state.get("user") or {}).get("role") or "client").lower()
    return "ceo" if role in {"ceo", "admin", "owner"} else role


def _is_ceo(role: str | None = None) -> bool:
    return _safe_role(role) == "ceo"


def _safe_user_id(role: str) -> str:
    user = st.session_state.get("user") or {}
    return str(user.get("id") or user.get("username") or user.get("email") or role or "guest")


def _valid_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url).strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _now_ny() -> datetime:
    return datetime.now(ZoneInfo(DEFAULT_TZ))


def _week_start_sunday(dt: datetime | None = None) -> datetime:
    dt = dt or _now_ny()
    days_since_sunday = (dt.weekday() + 1) % 7
    start = datetime.combine((dt - timedelta(days=days_since_sunday)).date(), time.min, tzinfo=ZoneInfo(DEFAULT_TZ))
    return start


def _weekly_zoom_cleanup() -> None:
    """Deletes old classes once per Sunday/week, so schedules do not stack forever."""
    now = _now_ny()
    current_week = _week_start_sunday(now)
    cleanup_key = "last_zoom_cleanup_week_start"
    week_value = current_week.date().isoformat()
    with _connect() as con:
        row = con.execute("SELECT value FROM cleanup_state WHERE key=?", (cleanup_key,)).fetchone()
        if row and row["value"] == week_value:
            return
        # Keep current upcoming week plus recent previous entries until the next Sunday cleanup runs.
        con.execute("DELETE FROM zoom_classes WHERE datetime(start_at) < datetime(?)", (current_week.isoformat(),))
        con.execute("""
            INSERT INTO cleanup_state(key, value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (cleanup_key, week_value))
        con.commit()


def _insert_zoom(row: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute("""
            INSERT INTO zoom_classes(id,title,start_at,end_at,timezone,zoom_url,room_name,description,level,created_by,created_at,updated_at)
            VALUES(:id,:title,:start_at,:end_at,:timezone,:zoom_url,:room_name,:description,:level,:created_by,:created_at,:updated_at)
        """, {**row, "id": row.get("id") or uuid.uuid4().hex, "created_at": now, "updated_at": now})
        con.commit()


def _update_zoom(zoom_id: str, row: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    row = {**row, "id": zoom_id, "updated_at": now}
    with _connect() as con:
        con.execute("""
            UPDATE zoom_classes SET
              title=:title,start_at=:start_at,end_at=:end_at,timezone=:timezone,zoom_url=:zoom_url,
              room_name=:room_name,description=:description,level=:level,updated_at=:updated_at
            WHERE id=:id
        """, row)
        con.commit()


def _delete_zoom(zoom_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM zoom_classes WHERE id=?", (zoom_id,))
        con.commit()


def _load_zoom_classes() -> list[dict[str, Any]]:
    _weekly_zoom_cleanup()
    start = _week_start_sunday(_now_ny())
    end = start + timedelta(days=8)  # current week and a little Sunday buffer
    with _connect() as con:
        rows = con.execute("""
            SELECT * FROM zoom_classes
            WHERE datetime(start_at) >= datetime(?) AND datetime(start_at) < datetime(?)
            ORDER BY datetime(start_at) ASC
        """, (start.isoformat(), end.isoformat())).fetchall()
    return [dict(r) for r in rows]


def _insert_video(con: sqlite3.Connection, item: dict[str, Any], commit: bool = True) -> None:
    now = datetime.now(timezone.utc).isoformat()
    con.execute("""
        INSERT INTO education_videos(id,title,url,channel,track,description,featured,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (item.get("id") or uuid.uuid4().hex, item.get("title",""), item.get("url",""), item.get("channel",""), item.get("track","Foundation"), item.get("description",""), int(item.get("featured",0)), now, now))
    if commit:
        con.commit()


def _save_video(item: dict[str, Any], video_id: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        if video_id:
            con.execute("""
                UPDATE education_videos SET title=?,url=?,channel=?,track=?,description=?,featured=?,updated_at=? WHERE id=?
            """, (item["title"], item["url"], item.get("channel",""), item.get("track","Foundation"), item.get("description",""), int(item.get("featured",0)), now, video_id))
        else:
            _insert_video(con, item, commit=False)
        con.commit()


def _delete_video(video_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM education_videos WHERE id=?", (video_id,))
        con.commit()


def _load_videos() -> list[dict[str, Any]]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM education_videos ORDER BY featured DESC, datetime(updated_at) DESC").fetchall()
    return [dict(r) for r in rows]


def _save_custom_course(item: dict[str, Any], course_id: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": course_id or uuid.uuid4().hex,
        "track": item.get("track", "Custom"),
        "title": item.get("title", "Untitled Course"),
        "level": item.get("level", "All levels"),
        "time": item.get("time", "30 min"),
        "outcome": item.get("outcome", ""),
        "overview": item.get("overview", ""),
        "deep_dive": item.get("deep_dive", ""),
        "process": item.get("process", ""),
        "mistakes": item.get("mistakes", ""),
        "drill": item.get("drill", ""),
        "is_active": int(item.get("is_active", 1)),
        "updated_at": now,
    }
    with _connect() as con:
        if course_id:
            con.execute("""
                UPDATE custom_courses SET track=:track,title=:title,level=:level,time=:time,outcome=:outcome,overview=:overview,
                deep_dive=:deep_dive,process=:process,mistakes=:mistakes,drill=:drill,is_active=:is_active,updated_at=:updated_at WHERE id=:id
            """, payload)
        else:
            payload["created_at"] = now
            con.execute("""
                INSERT INTO custom_courses(id,track,title,level,time,outcome,overview,deep_dive,process,mistakes,drill,is_active,created_at,updated_at)
                VALUES(:id,:track,:title,:level,:time,:outcome,:overview,:deep_dive,:process,:mistakes,:drill,:is_active,:created_at,:updated_at)
            """, payload)
        con.commit()


def _delete_custom_course(course_id: str) -> None:
    with _connect() as con:
        con.execute("DELETE FROM custom_courses WHERE id=?", (course_id,))
        con.commit()


def _load_custom_courses() -> list[dict[str, Any]]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM custom_courses WHERE is_active=1 ORDER BY datetime(updated_at) DESC").fetchall()
    courses = []
    for r in rows:
        d = dict(r)
        courses.append({
            "id": d["id"], "track": d["track"], "title": d["title"], "level": d.get("level") or "All levels", "time": d.get("time") or "30 min",
            "outcome": d.get("outcome") or "", "overview": d.get("overview") or "",
            "deep_dive": [("CEO Lesson", x.strip()) for x in (d.get("deep_dive") or "").split("\n") if x.strip()],
            "process": [x.strip() for x in (d.get("process") or "").split("\n") if x.strip()],
            "mistakes": [x.strip() for x in (d.get("mistakes") or "").split("\n") if x.strip()],
            "drill": d.get("drill") or "",
            "custom": True,
        })
    return courses

# ───────────────────────────── styling / helpers ─────────────────────────────

def _load_css() -> None:
    if STYLE_PATH.exists():
        st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .edu-hero{padding:1.4rem;border-radius:24px;background:linear-gradient(135deg,rgba(9,14,28,.98),rgba(25,31,48,.94));border:1px solid rgba(255,255,255,.12);margin-bottom:1rem}.edu-card,.edu-panel{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:1rem}.edu-muted{color:rgba(255,255,255,.68)}.edu-pill{display:inline-block;border-radius:999px;padding:.25rem .6rem;background:rgba(0,255,163,.09);border:1px solid rgba(0,255,163,.24);color:#aaffdf;margin:.12rem;font-size:.78rem;font-weight:800}
        div[data-baseweb="select"]>div{background:#101827!important;color:#fff!important;border-color:rgba(255,255,255,.16)!important}
        </style>
        """, unsafe_allow_html=True)


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _split_lines(value: str) -> list[str]:
    return [x.strip() for x in str(value or "").splitlines() if x.strip()]


def _video_embed_url(url: str) -> str | None:
    url = str(url or "").strip()
    if not _valid_url(url):
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if "youtube.com" in host:
        if parsed.path.startswith("/watch"):
            # parse manually to avoid importing parse_qs just for this small case
            match = re.search(r"[?&]v=([^&]+)", url)
            if match:
                return f"https://www.youtube.com/embed/{match.group(1)}"
        if parsed.path.startswith("/embed/"):
            return url
        if parsed.path.startswith("/shorts/"):
            vid = parsed.path.split("/")[2]
            return f"https://www.youtube.com/embed/{vid}"
    if "youtu.be" in host:
        vid = parsed.path.strip("/").split("/")[0]
        if vid:
            return f"https://www.youtube.com/embed/{vid}"
    if "vimeo.com" in host:
        vid = parsed.path.strip("/").split("/")[0]
        if vid.isdigit():
            return f"https://player.vimeo.com/video/{vid}"
    return None


def _format_dt(iso_value: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(DEFAULT_TZ))
        return dt.astimezone(ZoneInfo(DEFAULT_TZ)).strftime("%a, %b %d · %I:%M %p %Z")
    except Exception:
        return iso_value


def _track_options(courses: list[dict[str, Any]]) -> list[str]:
    tracks = sorted({c.get("track", "General") for c in courses})
    preferred = ["Foundation", "Smart Money", "Market Profile", "Execution", "Mindset", "Review"]
    ordered = [x for x in preferred if x in tracks] + [x for x in tracks if x not in preferred]
    return ["All"] + ordered

# ───────────────────────────── render components ─────────────────────────────

def _hero(role: str) -> None:
    st.markdown(f"""
    <div class="edu-hero">
      <div class="edu-orb"></div>
      <div class="edu-kicker">Dropz Universal Agent · Trader Growth System</div>
      <h1>Trader Education Center</h1>
      <p>{_esc(_setting('announcement', DEFAULT_SETTINGS['announcement']))}</p>
      <div class="edu-badge-row">
        <span class="edu-badge">Full Learning Paths</span>
        <span class="edu-badge">Live Zoom Classes</span>
        <span class="edu-badge">Video Lessons</span>
        <span class="edu-badge">Quiz Review</span>
        <span class="edu-badge">Volume Profile</span>
        <span class="edu-badge">Timeframe Mastery</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _overview_cards(courses: list[dict[str, Any]], videos: list[dict[str, Any]], zooms: list[dict[str, Any]]) -> None:
    tracks = len({c.get("track", "General") for c in courses})
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="edu-stat-card"><span>Courses</span><strong>{len(courses)}</strong><small>Deep learning modules</small></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="edu-stat-card"><span>Tracks</span><strong>{tracks}</strong><small>Foundation to advanced</small></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="edu-stat-card"><span>Videos</span><strong>{len(videos)}</strong><small>CEO-managed lessons</small></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="edu-stat-card"><span>This Week</span><strong>{len(zooms)}</strong><small>Live classes posted</small></div>', unsafe_allow_html=True)


def _render_course_card(course: dict[str, Any], idx: int) -> None:
    deep = course.get("deep_dive", [])
    process = course.get("process", [])
    mistakes = course.get("mistakes", [])
    with st.expander(f"{idx}. {course['title']}  ·  {course.get('track','General')}  ·  {course.get('time','')}", expanded=False):
        st.markdown(f"""
        <div class="edu-course-head">
          <div><span class="edu-pill edu-pill-green">{_esc(course.get('track','General'))}</span><span class="edu-pill edu-pill-gold">{_esc(course.get('level','All levels'))}</span><span class="edu-pill">{_esc(course.get('time',''))}</span></div>
          <h3>{_esc(course['title'])}</h3>
          <p>{_esc(course.get('overview',''))}</p>
          <div class="edu-outcome"><b>Outcome:</b> {_esc(course.get('outcome',''))}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="edu-subtitle">Full-depth lesson material</div>', unsafe_allow_html=True)
        for title, body in deep:
            st.markdown(f"""
            <div class="edu-depth-block">
              <div class="edu-depth-title">{_esc(title)}</div>
              <div class="edu-muted">{_esc(body)}</div>
            </div>
            """, unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="edu-subtitle">Execution process</div>', unsafe_allow_html=True)
            for step in process:
                st.markdown(f'<div class="edu-check">✓ {_esc(step)}</div>', unsafe_allow_html=True)
        with col_b:
            st.markdown('<div class="edu-subtitle">Mistakes to avoid</div>', unsafe_allow_html=True)
            for m in mistakes:
                st.markdown(f'<div class="edu-warn">× {_esc(m)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="edu-drill"><b>Practice drill:</b> {_esc(course.get("drill", ""))}</div>', unsafe_allow_html=True)


def _tab_courses(role: str, courses: list[dict[str, Any]]) -> None:
    st.markdown('<div class="edu-section-title">Learning paths</div>', unsafe_allow_html=True)
    st.caption("Each course opens into a full-depth lesson. Use the filter to focus on the part of trading you want to master.")
    left, right = st.columns([1.2, 2])
    with left:
        track = st.selectbox("Course track", _track_options(courses), key="edu_course_track")
    with right:
        search = st.text_input("Search lessons", placeholder="Example: volume profile, timeframe, FVG, risk...", key="edu_course_search")
    filtered = [c for c in courses if track == "All" or c.get("track") == track]
    if search.strip():
        s = search.lower().strip()
        filtered = [c for c in filtered if s in (c.get("title","")+" "+c.get("overview","")+" "+c.get("track","")).lower()]
    for i, course in enumerate(filtered, 1):
        _render_course_card(course, i)

    if _is_ceo(role):
        with st.expander("CEO · Subtle course controls", expanded=False):
            st.caption("Add extra courses without changing the page title or breaking the default curriculum. Clients see active CEO courses immediately.")
            with st.form("edu_add_course_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                title = c1.text_input("Course title")
                track_new = c2.text_input("Track", value="Custom")
                level = c3.text_input("Level", value="All levels")
                time_est = c1.text_input("Time", value="30 min")
                outcome = c2.text_input("Outcome")
                overview = st.text_area("Overview", height=90)
                deep = st.text_area("Lesson body — one teaching paragraph per line", height=140)
                process = st.text_area("Execution process — one step per line", height=100)
                mistakes = st.text_area("Mistakes to avoid — one per line", height=100)
                drill = st.text_area("Practice drill", height=80)
                if st.form_submit_button("Add Course For All Users", use_container_width=True):
                    if not title.strip():
                        st.error("Course title is required.")
                    else:
                        _save_custom_course({"title": title, "track": track_new, "level": level, "time": time_est, "outcome": outcome, "overview": overview, "deep_dive": deep, "process": process, "mistakes": mistakes, "drill": drill})
                        st.success("Course added for all users.")
                        st.rerun()
            custom = _load_custom_courses()
            if custom:
                st.markdown("#### Remove custom course")
                choices = {f"{c['track']} · {c['title']}": c["id"] for c in custom}
                pick = st.selectbox("Custom courses", list(choices.keys()), key="edu_delete_course_pick")
                if st.button("Delete Selected Custom Course", use_container_width=True, key="edu_delete_course_btn"):
                    _delete_custom_course(choices[pick])
                    st.success("Custom course deleted for all users.")
                    st.rerun()


def _tab_quiz(courses: list[dict[str, Any]]) -> None:
    st.markdown('<div class="edu-section-title">Quiz center</div>', unsafe_allow_html=True)
    tracks = ["All"] + sorted({q["track"] for q in QUIZ_BANK})
    track = st.selectbox("Quiz focus", tracks, key="edu_quiz_track")
    questions = [q for q in QUIZ_BANK if track == "All" or q["track"] == track]
    answers = {}
    for i, q in enumerate(questions, 1):
        st.markdown(f'<div class="edu-quiz-question">{i}. {_esc(q["question"])}</div>', unsafe_allow_html=True)
        answers[q["id"]] = st.radio("Choose one", q["options"], key=f"quiz_{track}_{q['id']}", label_visibility="collapsed")
    if st.button("Check Quiz", use_container_width=True, key="edu_check_quiz"):
        correct = 0
        review_html = ""
        for i, q in enumerate(questions, 1):
            chosen = answers.get(q["id"])
            ok = chosen == q["answer"]
            correct += int(ok)
            cls = "edu-review-ok" if ok else "edu-review-bad"
            label = "Correct" if ok else "Wrong"
            review_html += f"""
            <div class="edu-review {cls}">
              <b>{i}. {label}</b><br>
              <span class="edu-muted">Question: {_esc(q['question'])}</span><br>
              <span>Your answer: <b>{_esc(chosen)}</b></span><br>
              <span>Correct answer: <b>{_esc(q['answer'])}</b></span><br>
              <span class="edu-muted">Why: {_esc(q['explain'])}</span>
            </div>
            """
        score_pct = (correct / len(questions) * 100) if questions else 0
        st.markdown(f'<div class="edu-score-card"><strong>{correct}/{len(questions)}</strong><span>{score_pct:.0f}% score</span></div>', unsafe_allow_html=True)
        st.markdown(review_html, unsafe_allow_html=True)


def _tab_zoom(role: str) -> None:
    st.markdown('<div class="edu-section-title">Live Zoom classroom</div>', unsafe_allow_html=True)
    room_name = _setting("zoom_room_name", DEFAULT_SETTINGS["zoom_room_name"])
    room_url = _setting("zoom_room_url", DEFAULT_SETTINGS["zoom_room_url"])
    room_note = _setting("zoom_room_note", DEFAULT_SETTINGS["zoom_room_note"])
    valid_room = _valid_url(room_url)
    st.markdown(f"""
    <div class="edu-zoom-room">
      <div>
        <div class="edu-kicker">Main learning room</div>
        <h3>{_esc(room_name)}</h3>
        <p>{_esc(room_note)}</p>
      </div>
      <a class="edu-join-btn" href="{_esc(room_url if valid_room else 'https://zoom.us/')}" target="_blank">Join Main Room</a>
    </div>
    """, unsafe_allow_html=True)
    if not valid_room:
        st.warning("CEO needs to add a valid https:// Zoom or meeting room link for the main room.")

    classes = _load_zoom_classes()
    if classes:
        for cls in classes:
            st.markdown(f"""
            <div class="edu-class-card">
              <div class="edu-class-date">{_esc(_format_dt(cls['start_at']))}</div>
              <h4>{_esc(cls['title'])}</h4>
              <p>{_esc(cls.get('description') or '')}</p>
              <div><span class="edu-pill edu-pill-green">{_esc(cls.get('level') or 'Live Class')}</span><span class="edu-pill">{_esc(cls.get('room_name') or room_name)}</span></div>
              <a class="edu-small-link" href="{_esc(cls['zoom_url'])}" target="_blank">Join this class</a>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="edu-empty">No live classes posted for the current upcoming week yet.</div>', unsafe_allow_html=True)

    if _is_ceo(role):
        with st.expander("CEO · Zoom controls", expanded=False):
            st.caption("Only Zoom/classes are editable here. Page title stays locked. All clients see what the CEO posts.")
            with st.form("edu_zoom_room_form"):
                rn = st.text_input("Main room name", value=room_name)
                ru = st.text_input("Main Zoom / room link", value=room_url)
                note = st.text_area("Main room note", value=room_note, height=80)
                if st.form_submit_button("Save Main Room For All Users", use_container_width=True):
                    if not _valid_url(ru):
                        st.error("Add a valid https:// link.")
                    else:
                        _save_setting("zoom_room_name", rn.strip() or DEFAULT_SETTINGS["zoom_room_name"])
                        _save_setting("zoom_room_url", ru.strip())
                        _save_setting("zoom_room_note", note.strip())
                        st.success("Main room saved for all users.")
                        st.rerun()
            st.markdown("#### Add a class for this week")
            with st.form("edu_add_zoom_class", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                title = c1.text_input("Class title")
                class_date = c2.date_input("Date", value=_now_ny().date())
                class_time = c3.time_input("Start time", value=time(19, 0))
                duration = c1.number_input("Duration minutes", min_value=15, max_value=240, value=60, step=15)
                level = c2.selectbox("Level", ["All levels", "Beginner", "Intermediate", "Advanced", "Live Market Review"])
                zoom_url = c3.text_input("Class link", value=room_url if valid_room else "https://zoom.us/")
                room = st.text_input("Room / host label", value=room_name)
                desc = st.text_area("Description", placeholder="What users will learn in this class...", height=90)
                if st.form_submit_button("Post Zoom Class For All Users", use_container_width=True):
                    if not title.strip():
                        st.error("Class title is required.")
                    elif not _valid_url(zoom_url):
                        st.error("Class link must be a valid https:// link.")
                    else:
                        start = datetime.combine(class_date, class_time, tzinfo=ZoneInfo(DEFAULT_TZ))
                        end = start + timedelta(minutes=int(duration))
                        _insert_zoom({"title": title.strip(), "start_at": start.isoformat(), "end_at": end.isoformat(), "timezone": DEFAULT_TZ, "zoom_url": zoom_url.strip(), "room_name": room.strip(), "description": desc.strip(), "level": level, "created_by": _safe_user_id(role)})
                        st.success("Zoom class posted for all users.")
                        st.rerun()
            if classes:
                st.markdown("#### Edit or delete visible classes")
                class_choices = {f"{_format_dt(c['start_at'])} · {c['title']}": c for c in classes}
                pick = st.selectbox("Select class", list(class_choices.keys()), key="edu_zoom_edit_pick")
                chosen = class_choices[pick]
                with st.form("edu_edit_zoom_class"):
                    etitle = st.text_input("Title", value=chosen["title"])
                    eurl = st.text_input("Link", value=chosen["zoom_url"])
                    eroom = st.text_input("Room", value=chosen.get("room_name") or room_name)
                    edesc = st.text_area("Description", value=chosen.get("description") or "", height=90)
                    elevel = st.selectbox("Level", ["All levels", "Beginner", "Intermediate", "Advanced", "Live Market Review"], index=0)
                    b1, b2 = st.columns(2)
                    save = b1.form_submit_button("Save Class Changes", use_container_width=True)
                    delete = b2.form_submit_button("Delete Class", use_container_width=True)
                if save:
                    if not _valid_url(eurl):
                        st.error("Link must be a valid https:// link.")
                    else:
                        _update_zoom(chosen["id"], {"title": etitle, "start_at": chosen["start_at"], "end_at": chosen["end_at"], "timezone": chosen["timezone"], "zoom_url": eurl, "room_name": eroom, "description": edesc, "level": elevel})
                        st.success("Class updated for all users.")
                        st.rerun()
                if delete:
                    _delete_zoom(chosen["id"])
                    st.success("Class deleted for all users.")
                    st.rerun()


def _tab_videos(role: str) -> None:
    st.markdown('<div class="edu-section-title">Video learning library</div>', unsafe_allow_html=True)
    videos = _load_videos()
    tracks = ["All"] + sorted({v.get("track") or "General" for v in videos})
    selected = st.selectbox("Video category", tracks, key="edu_video_track")
    filtered = [v for v in videos if selected == "All" or (v.get("track") or "General") == selected]
    if filtered:
        for i in range(0, len(filtered), 2):
            cols = st.columns(2)
            for col, vid in zip(cols, filtered[i:i+2]):
                with col:
                    embed = _video_embed_url(vid["url"])
                    st.markdown('<div class="edu-video-box">', unsafe_allow_html=True)
                    if embed:
                        st.markdown(f'<iframe class="edu-video-frame" src="{_esc(embed)}" allowfullscreen></iframe>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="edu-video-placeholder">Video preview unavailable for this link. Use the channel button below.</div>', unsafe_allow_html=True)
                    st.markdown(f"""
                        <h4>{_esc(vid['title'])}</h4>
                        <p>{_esc(vid.get('description') or '')}</p>
                        <div><span class="edu-pill edu-pill-green">{_esc(vid.get('track') or 'General')}</span><span class="edu-pill">{_esc(vid.get('channel') or 'Channel')}</span></div>
                        <a class="edu-small-link" href="{_esc(vid['url'])}" target="_blank">Open channel / video</a>
                    """, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="edu-empty">No videos in this category yet.</div>', unsafe_allow_html=True)

    if _is_ceo(role):
        with st.expander("CEO · Video controls", expanded=False):
            st.caption("Add YouTube, Vimeo, Zoom replay, or channel links. YouTube/Vimeo links embed when possible; all links open externally too.")
            with st.form("edu_add_video", clear_on_submit=True):
                c1, c2 = st.columns(2)
                title = c1.text_input("Video title")
                url = c2.text_input("Video or channel link")
                channel = c1.text_input("Channel / source", value="Dropz Education")
                track = c2.selectbox("Category", ["Foundation", "Smart Money", "Market Profile", "Execution", "Mindset", "Review", "Custom"])
                desc = st.text_area("Description", height=90)
                featured = st.checkbox("Feature near top", value=False)
                if st.form_submit_button("Add Video For All Users", use_container_width=True):
                    if not title.strip():
                        st.error("Video title is required.")
                    elif not _valid_url(url):
                        st.error("Add a valid https:// video or channel link.")
                    else:
                        _save_video({"title": title.strip(), "url": url.strip(), "channel": channel.strip(), "track": track, "description": desc.strip(), "featured": int(featured)})
                        st.success("Video added for all users.")
                        st.rerun()
            if videos:
                st.markdown("#### Delete video")
                choices = {f"{v.get('track','')} · {v['title']}": v["id"] for v in videos}
                pick = st.selectbox("Current videos", list(choices.keys()), key="edu_delete_video_pick")
                if st.button("Delete Selected Video", use_container_width=True, key="edu_delete_video_btn"):
                    _delete_video(choices[pick])
                    st.success("Video deleted for all users.")
                    st.rerun()


def _tab_notes() -> None:
    st.markdown('<div class="edu-section-title">Practice worksheet</div>', unsafe_allow_html=True)
    st.caption("These notes are session-based and do not replace your real Trade Journal/Trade Log.")
    c1, c2 = st.columns(2)
    with c1:
        st.text_area("Today’s market lesson", height=150, placeholder="Example: Asia built equal highs, London swept them, NY accepted above VAH...", key="edu_note_lesson")
        st.text_area("My strongest setup", height=140, placeholder="Which setup did I see clearly today?", key="edu_note_setup")
    with c2:
        st.text_area("Mistake or risk warning", height=150, placeholder="What would have hurt me today?", key="edu_note_warning")
        st.text_area("Tomorrow’s plan", height=140, placeholder="Bias, key levels, session, max risk, no-trade window...", key="edu_note_plan")
    if st.button("Save Worksheet In This Session", use_container_width=True, key="edu_save_worksheet"):
        st.session_state["edu_saved_worksheet"] = {
            "lesson": st.session_state.get("edu_note_lesson", ""),
            "setup": st.session_state.get("edu_note_setup", ""),
            "warning": st.session_state.get("edu_note_warning", ""),
            "plan": st.session_state.get("edu_note_plan", ""),
            "saved_at": datetime.now().isoformat(),
        }
        st.success("Worksheet saved in this Streamlit session.")


def render_education_page(role: str = "client") -> None:
    _init_db()
    role = _safe_role(role)
    _load_css()
    courses = COURSE_LIBRARY + _load_custom_courses()
    videos = _load_videos()
    zooms = _load_zoom_classes()

    _hero(role)
    _overview_cards(courses, videos, zooms)

    if _is_ceo(role):
        with st.expander("CEO · Page-wide announcement", expanded=False):
            st.caption("Only the announcement text is editable here. The page title stays locked so the app remains consistent.")
            with st.form("edu_announcement_form"):
                ann = st.text_area("Announcement shown to all users", value=_setting("announcement", DEFAULT_SETTINGS["announcement"]), height=90)
                if st.form_submit_button("Save Announcement", use_container_width=True):
                    _save_setting("announcement", ann.strip() or DEFAULT_SETTINGS["announcement"])
                    st.success("Announcement updated for all users.")
                    st.rerun()

    tab_courses, tab_quiz, tab_zoom, tab_videos, tab_notes = st.tabs([
        "🎓 Courses", "🧠 Quizzes", "🎥 Live Zoom", "📺 Videos", "📝 Worksheet"
    ])
    with tab_courses:
        _tab_courses(role, courses)
    with tab_quiz:
        _tab_quiz(courses)
    with tab_zoom:
        _tab_zoom(role)
    with tab_videos:
        _tab_videos(role)
    with tab_notes:
        _tab_notes()


def render_frontend_education_page(role: str = "client") -> None:
    render_education_page(role)

# Backward-compatible aliases so old Accounts imports/routes do not break during the rename.
def render_trading_accounts_page(role: str = "client") -> None:
    render_education_page(role)

def render_accounts(role: str = "client") -> None:
    render_education_page(role)

def render_frontend_accounts_page(role: str = "client") -> None:
    render_education_page(role)

if __name__ == "__main__":
    st.set_page_config(page_title="Education", page_icon="🎓", layout="wide")
    render_education_page("ceo")
