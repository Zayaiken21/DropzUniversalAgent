
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


# ───────────────────────────── expanded production curriculum ─────────────────────────────
# These defaults are intentionally plain Python lists so the CEO/dev can edit them locally,
# while CEO-added courses/videos/Zoom classes continue to persist globally in SQLite.
# Data extension endpoints: COURSE_LIBRARY, QUIZ_BANK, DEFAULT_VIDEOS, and the CEO tables
# custom_courses, education_videos, zoom_classes, education_settings inside data/education_center.db.

COURSE_LIBRARY.extend([{'id': 'gold-usd-history', 'track': 'Market History', 'title': 'Gold, USD, and the Modern Market System', 'level': 'Beginner → Advanced', 'time': '90 min', 'outcome': 'Understand why gold reacts to USD strength, inflation fears, rates, crises, and central-bank policy.', 'overview': 'Gold is not just a chart symbol. XAUUSD sits at the intersection of money history, reserve currency confidence, inflation expectations, real yields, central-bank reserves, futures liquidity, and fear/risk appetite. This course gives users the background to understand why gold can trend during uncertainty and violently reverse when USD/rate expectations change.', 'deep_dive': [('Gold as money and store of value', 'For thousands of years gold has been treated as scarce, durable, portable value. Modern traders do not need to romanticize it, but they should understand why gold still becomes a safety and inflation narrative when confidence weakens.'), ('The USD anchor', 'Gold is quoted globally in USD. When the dollar strengthens, each ounce of gold can become more expensive for non-dollar buyers, often creating pressure. When dollar confidence weakens, gold can benefit as an alternative reserve asset.'), ('Rates and real yields', 'Gold does not pay interest. When real yields rise, holding cash or bonds can become more attractive. When real yields fall or inflation fear rises, gold can become more attractive as a hedge.'), ('Central banks and reserves', 'Central banks hold gold as part of reserve diversification. Large accumulation themes can support long-term sentiment, but intraday traders still need price confirmation.'), ('Crisis behavior', 'During war scares, banking stress, inflation shocks, debt-ceiling concerns, or liquidity stress, gold can spike. The first move is often emotional; the professional waits for spreads, liquidity, and structure to normalize.'), ('Trading takeaway', 'Do not trade gold from history alone. Use history for bias awareness, then use structure, liquidity, volume profile, sessions, and risk controls for execution.')], 'process': ['Check USD/DXY direction', 'Check real-yield/rate narrative', 'Mark gold higher-timeframe levels', 'Wait for session confirmation', 'Avoid entering purely from headlines'], 'mistakes': ['Buying gold only because news sounds scary', 'Ignoring USD strength', 'Trading CPI/FOMC candles without a plan', 'Confusing macro bias with entry timing'], 'drill': 'Before the New York session, write whether the day is gold-positive, gold-negative, or neutral from USD/rates/news, then compare that bias to the actual 15M structure.'}, {'id': 'time-sales-tape-reading', 'track': 'Order Flow', 'title': 'Time & Sales Tape Reading: Speed, Size, Absorption, and Traps', 'level': 'Intermediate', 'time': '75 min', 'outcome': 'Use tape behavior as confirmation instead of reacting emotionally to fast prints.', 'overview': 'The tape shows transactions hitting the market. It can reveal urgency, absorption, hidden interest, and false breakout behavior. This course turns tape reading into a repeatable observation drill rather than a reason to chase candles.', 'deep_dive': [('Print speed', 'Fast prints often mean momentum or urgency. Slow prints near a level can show caution or indecision. Speed matters most when it appears at a key level already marked on the chart.'), ('Size and clusters', 'Large prints at the ask can show aggressive buying; large prints at the bid can show aggressive selling. Clusters are more important when they repeat around support, resistance, POC, VAH, VAL, or prior highs/lows.'), ('Price response', 'The question is not only whether prints are green or red. Ask: is price moving because of the tape or despite it? Strong buying that cannot lift price can signal absorption.'), ('Refreshing/hidden orders', 'Repeated prints at the same price can hint that a larger buyer/seller is absorbing flow. This is useful only when combined with structure and level context.'), ('Trap behavior', 'Fast green tape into a lower high or resistance that fails to advance can become a bull trap. Fast red tape into a higher low that fails to break can become a bear trap.'), ('Drill mindset', 'Watch a 10–15 minute window without trading. Record speed, size, color dominance, absorption, and what happened afterward. Pattern recognition comes from repetition.')], 'process': ['Choose a 15-minute window', 'Mark key level before watching tape', 'Record speed and size', 'Compare tape to price movement', 'Log whether follow-through happened'], 'mistakes': ['Chasing the first fast print', 'Ignoring the chart level', 'Treating color as a signal by itself', 'Using tape with no risk plan'], 'drill': 'For five sessions, observe one 15-minute window and write whether price moved with the tape, against the tape, or stalled despite aggressive prints.'}, {'id': 'volume-profile-complete', 'track': 'Market Profile', 'title': 'Volume Profile Complete: POC, VAH, VAL, HVN, LVN, Acceptance, Rejection', 'level': 'Intermediate → Advanced', 'time': '105 min', 'outcome': 'Build trades around value instead of random levels.', 'overview': 'Volume profile shows where business was done. POC marks the heaviest traded price, VAH/VAL frame the value area, HVNs show accepted zones, and LVNs show low-participation air pockets. The goal is to know whether price is accepting value, rejecting it, or rotating back to it.', 'deep_dive': [('POC', 'Point of Control is the price with the most traded volume in the selected range. It can act like a magnet, pivot, or decision level because many participants transacted there.'), ('VAH and VAL', 'Value Area High and Value Area Low frame where a large percentage of volume occurred. Acceptance above VAH can support continuation; rejection back inside value can support rotation.'), ('HVN and LVN', 'High Volume Nodes represent accepted prices where market participants agreed. Low Volume Nodes represent thin areas where price may move quickly because less business was done.'), ('Weekly vs daily profile', 'Weekly profiles help plan the bigger auction. Daily profiles help intraday execution. A prior weekly POC can be a major target while the current daily VAL can be an entry decision zone.'), ('Swing profile', 'Applying a profile to a specific swing helps locate internal POC/VAH/VAL. This can refine entries after a swing forms near a higher-timeframe key level.'), ('Acceptance and rejection', 'A wick through VAH/VAL is not enough. Watch closes, retests, speed, and whether price holds outside value or falls back inside.'), ('Trade framework', 'Trend days hold outside value. Range days rotate between value edges. Reversal days reject an edge and travel back through value toward POC/opposite edge.')], 'process': ['Pick the correct profile range', 'Mark POC/VAH/VAL', 'Identify HVNs/LVNs', 'Decide acceptance or rejection', 'Align entry with structure and risk'], 'mistakes': ['Drawing profile on random ranges', 'Buying VAH without acceptance', 'Selling VAL without rejection', 'Ignoring session context'], 'drill': 'On XAUUSD, draw yesterday’s profile and today’s developing profile. Record whether price accepted above VAH, rejected VAL, or rotated to POC.'}, {'id': 'multi-timeframe-blueprint', 'track': 'Execution', 'title': 'Multi-Timeframe Blueprint: Monthly, Weekly, Daily, 4H, 1H, 15M, 5M, 1M', 'level': 'Beginner → Advanced', 'time': '110 min', 'outcome': 'Know exactly what each timeframe is responsible for and stop mixing signals.', 'overview': 'A trader does not need every timeframe to say the same thing. A professional assigns each timeframe a job. Higher timeframes define context; middle timeframes define opportunity; lower timeframes refine execution and risk.', 'deep_dive': [('Monthly/Weekly', 'Use these for macro direction, major highs/lows, multi-month support/resistance, and where institutions may care. They are not entry charts for scalpers.'), ('Daily/4H', 'Use these for swing bias, previous day/week levels, premium/discount, and key news reaction zones. This is where you decide whether intraday trades are with or against larger context.'), ('1H/30M', 'Use these for intraday narrative: range, trend, session high/low, first displacement, and likely liquidity targets.'), ('15M/5M', 'Use these for setup validation: sweep, BOS, CHoCH, FVG, order block, or profile rejection. Many scalps should be filtered here before moving to 1M.'), ('1M', 'Use this only for entry refinement after the higher map is clear. It helps reduce stop size but can create false urgency.'), ('Alignment scoring', 'Give one point each for HTF bias, key level, session, volume/profile reaction, trigger candle, and risk/reward. Do not take trades with weak scores.')], 'process': ['Start at HTF', 'Mark levels', 'Drop to session timeframe', 'Wait for setup timeframe confirmation', 'Use 1M only for trigger', 'Score the setup'], 'mistakes': ['Letting 1M override daily bias', 'Changing bias every candle', 'Using too many indicators', 'Entering before setup timeframe closes'], 'drill': 'Take one historical day and write a top-down map from Daily to 1M before marking where the best entry actually appeared.'}, {'id': 'spx-options-execution', 'track': 'SPX / Indices', 'title': 'SPX and Index Options Execution: Contracts, Fills, Targets, Runners', 'level': 'Intermediate', 'time': '95 min', 'outcome': 'Understand index option trade management without getting trapped by P/L swings.', 'overview': 'Index options can move fast. The chart idea can be correct while the contract entry, spread, fill quality, or exit plan ruins the trade. This course teaches users to plan contracts, take partials, respect stops, and avoid marrying a play.', 'deep_dive': [('Contract selection', 'Choose contracts with enough liquidity and realistic spread. A good chart setup can still be bad if the option spread is too wide.'), ('Fills', 'Limit orders help prevent emotional chasing. If you miss a fill, do not turn a planned trade into a worse trade just to participate.'), ('Partial targets', 'Pre-planned partials can keep traders from staring at P/L and panic-selling. Example logic: first scale, second scale, runner only after risk is reduced.'), ('Stop discipline', 'If the stop condition triggers, exit and cancel remaining target orders. Hoping that a stopped setup comes back is how one trade becomes a large loss.'), ('News and volatility', 'Index options expand and contract with volatility. Around news, premiums can change sharply even if price direction looks right.')], 'process': ['Check liquidity/spread', 'Define chart invalidation', 'Plan contract stop', 'Place partial target rules', 'Cancel targets if stopped'], 'mistakes': ['Buying illiquid contracts', 'Chasing alerts', 'Ignoring spreads', 'Letting runners turn into losers', 'Not cancelling target orders after stop'], 'drill': 'Paper trade one SPX idea and write entry contract, spread, first target, second target, runner rule, and exact stop trigger before entry.'}, {'id': 'prior-day-levels', 'track': 'SPX / Indices', 'title': 'Prior Day High/Low, Premarket Range, and Intraday Key Areas', 'level': 'Intermediate', 'time': '70 min', 'outcome': 'Use prior day and session levels to avoid low-quality entries and identify reaction zones.', 'overview': 'Prior day highs/lows, premarket highs/lows, liquidity levels, and news reaction levels are not magic. They matter because many traders see them and orders often cluster there. The edge comes from waiting for reaction and confirmation.', 'deep_dive': [('PDH/PDL', 'Prior Day High and Low can act as liquidity, breakout, reversal, or continuation zones. The key is whether price accepts beyond them or rejects back inside range.'), ('Premarket range', 'For indices, premarket highs/lows frame early liquidity. NY open can sweep one side before choosing direction.'), ('Open, lunch, EOD', 'The open has volatility, lunch often compresses, and end of day can trend or rebalance. Each window has different execution rules.'), ('False confidence', 'A level is not a signal. A level plus sweep, displacement, retest, volume/profile reaction, and risk plan is a setup.')], 'process': ['Mark PDH/PDL', 'Mark premarket high/low', 'Wait for open range behavior', 'Watch acceptance/rejection', 'Target next liquidity'], 'mistakes': ['Entering because level was touched', 'Ignoring lunch chop', 'Assuming breakout without close', 'No target mapped'], 'drill': 'For five index sessions, mark PDH/PDL before the open and record whether they acted as breakout, rejection, or magnet.'}, {'id': 'candlestick-patterns-truth', 'track': 'Price Action', 'title': 'Candlesticks and Chart Patterns: Confirmation Over Memorization', 'level': 'Beginner → Intermediate', 'time': '100 min', 'outcome': 'Use candles and patterns as context, not as isolated buy/sell commands.', 'overview': 'Candlestick and chart patterns can help define behavior, but no pattern guarantees outcome. The professional approach is identification guidelines, trend context, breakout direction, volume behavior, support/resistance, and failure planning.', 'deep_dive': [('Candles tell behavior', 'A wick shows rejection only when the surrounding context supports it. A strong body shows momentum, but it can also be exhaustion if it appears at a major target.'), ('Patterns need location', 'Double tops, rectangles, wedges, triangles, flags, head-and-shoulders, and diamonds behave differently depending on trend and where the breakout occurs.'), ('Breakout quality', 'Look for a decisive close, volume confirmation when available, and whether price accepts outside the pattern. Weak breakouts often throw back or pull back.'), ('Failure is information', 'A failed breakout can become a powerful trade in the opposite direction. Plan what failure looks like before entering.'), ('Statistics mindset', 'Pattern statistics are comparison tools, not guarantees. Your execution, market regime, stop placement, and timing determine your actual results.')], 'process': ['Identify pattern', 'Confirm trend/location', 'Wait for breakout/acceptance', 'Plan throwback/pullback', 'Define failure trade or exit'], 'mistakes': ['Trading pattern names only', 'Ignoring volume', 'Ignoring support/resistance', 'Expecting huge moves from every pattern'], 'drill': 'Find three rectangles or triangles. For each one, write breakout direction, pullback behavior, invalidation, and whether the move followed through.'}, {'id': 'elliott-fib-trendline', 'track': 'Technical Analysis', 'title': 'Elliott Wave, Fibonacci, Trendlines, Channels, and Protective Stops', 'level': 'Advanced', 'time': '120 min', 'outcome': 'Use technical tools to build scenarios without forcing predictions.', 'overview': 'Technical tools are strongest when they help define scenarios, targets, and invalidation. Wave counts, Fibonacci retracements/projections, trendlines, channels, and protective stops should work together with structure and risk, not replace them.', 'deep_dive': [('Wave principle', 'Wave analysis can help traders frame potential trend and correction paths, but the count must be confirmed by price action and invalidation levels.'), ('Fibonacci retracements', 'Common retracement zones can help plan pullback entries, but a Fibonacci level is not an entry by itself. Look for structure or order-flow confirmation at the zone.'), ('Fibonacci projections', 'Projections can help estimate targets after impulse legs. Targets should also align with liquidity, profile levels, prior highs/lows, or measured moves.'), ('Trendlines and channels', 'Trendlines help visualize rhythm and potential break/retest areas. Channels can project path and show when price is overextended.'), ('Protective stops', 'Different stop types—structure, volatility, time, technical, and catastrophic—serve different jobs. Choose the stop that matches the setup, not the emotion.')], 'process': ['Build scenario', 'Define invalidation', 'Find confluence', 'Wait for trigger', 'Use protective stop', 'Review if tool helped or distracted'], 'mistakes': ['Forcing wave counts', 'Entering from Fibonacci alone', 'Drawing trendlines after the fact', 'Moving stops because a count changes'], 'drill': 'Choose one trend and draw a channel, a Fibonacci retracement, and the structure stop. Decide if they agree or conflict.'}, {'id': 'setup-vs-entry-playbook', 'track': 'Playbook Building', 'title': 'Setup vs Entry: Building a Personal Playbook', 'level': 'Beginner → Advanced', 'time': '85 min', 'outcome': 'Separate market conditions from entry triggers so users stop taking random trades.', 'overview': 'A setup is the state where conditions are present. An entry is the precise trigger that allows execution. Confusing the two creates emotional trades. A playbook turns ideas into repeatable rules.', 'deep_dive': [('Setup definition', 'A setup might be a range breakout, fakeout, sweep, FVG retest, value rejection, or trend continuation. It describes the environment.'), ('Entry definition', 'An entry is the trigger: candle close, retest, lower-timeframe swing, double wick, engulfing candle, or profile reclaim.'), ('Why separation matters', 'A setup can be present for minutes or hours without an entry. Waiting protects traders from forcing early positions.'), ('Playbook rules', 'A professional playbook includes context, required levels, trigger, invalidation, target, no-trade filters, screenshots, and review criteria.'), ('Data loop', 'After 20+ occurrences, review whether the playbook is working. Keep what is measurable and remove vague rules.')], 'process': ['Name the setup', 'Define required context', 'Define exact entry', 'Define invalidation', 'Define target', 'Track results'], 'mistakes': ['Entering when only setup exists', 'Changing trigger mid-trade', 'No screenshot examples', 'No data review'], 'drill': 'Write one playbook card for your favorite setup using: Context, Setup, Entry, Stop, Target, Management, No-Trade Filter.'}, {'id': 'weekly-cycle-planning', 'track': 'Market Profile', 'title': 'Weekly Cycle Planning: Sunday Open, Weekly POC, Prior Week Levels', 'level': 'Intermediate', 'time': '80 min', 'outcome': 'Prepare the trading week around weekly anchors instead of reacting day by day.', 'overview': 'Weekly planning turns scattered intraday trades into a map. Sunday open, previous Sunday open, previous weekly high/low, weekly POC, weekly VAH/VAL, and early-week range give the trader anchors for targets and traps.', 'deep_dive': [('Sunday open', 'The first forex price after the weekend can act as a psychological anchor. Compare current Sunday open to previous Sunday open to sense weekly strength or weakness.'), ('Weekly POC', 'Once enough of the week has traded, the current weekly POC shows where the market has done the most business. Price can rotate back to it.'), ('Previous weekly value', 'Prior week VAH/VAL can become acceptance/rejection zones. A reclaim above PW VAH has a different meaning than rejection back below it.'), ('Early week behavior', 'Monday/Tuesday often builds information. If price sweeps one side and rejects, later sessions may target the opposite side.')], 'process': ['Mark Sunday open', 'Mark prior week H/L', 'Mark PW POC/VAH/VAL', 'Track early-week range', 'Use intraday setup only at weekly-relevant zones'], 'mistakes': ['Ignoring weekly context', 'Treating Monday chop as final direction', 'Forcing trades far from weekly levels', 'Not updating profile after two full days'], 'drill': 'Build a weekly map every Sunday night: SO, PSO, PWH, PWL, PW POC, PW VAH, PW VAL, and likely liquidity targets.'}, {'id': 'xauusd-news-macro', 'track': 'XAUUSD', 'title': 'XAUUSD News and Macro Execution: CPI, FOMC, NFP, DXY, Yields', 'level': 'Intermediate → Advanced', 'time': '95 min', 'outcome': 'Trade gold around news with structure instead of gambling on the headline candle.', 'overview': 'Gold reacts strongly to USD data, Fed expectations, real yields, geopolitical stress, and liquidity shocks. The safest education rule is simple: know when news is coming, define whether you trade before, during, or after it, and never improvise size during volatility.', 'deep_dive': [('High-impact news', 'CPI, PPI, NFP, FOMC, unemployment data, retail sales, PMI, and Fed speeches can create fast repricing in gold.'), ('DXY and yields', 'DXY strength and rising yields can pressure gold; dollar weakness and falling real yields can support it. Intraday exceptions happen, so price action still decides.'), ('Pre-news compression', 'Price may compress before news. Breakouts before the release can fail when liquidity is thin.'), ('Post-news model', 'Wait for the first impulse, the sweep or imbalance, then a structure break or value reclaim/rejection. The second clean setup is often safer than the first spike.'), ('Spread and slippage', 'MT5 spreads can widen around news. Your theoretical stop may not be the actual fill if liquidity is poor.')], 'process': ['Check calendar', 'Define no-trade window', 'Mark pre-news range', 'Wait for post-news structure', 'Reduce size or skip if spreads widen'], 'mistakes': ['Guessing CPI direction', 'Entering seconds before release', 'Using normal size during abnormal volatility', 'Ignoring DXY/yields'], 'drill': 'Replay one CPI day: mark the pre-news range, first impulse, sweep, structure break, FVG/profile level, and safest entry after volatility cooled.'}, {'id': 'psychology-discipline', 'track': 'Mindset', 'title': 'Trading Psychology: Discipline, Fear, Greed, Revenge, and Overconfidence', 'level': 'All levels', 'time': '100 min', 'outcome': 'Build rules that protect the trader from their own worst emotional states.', 'overview': 'Psychology is not motivational quotes. It is the operational system that prevents emotional states from changing risk, entries, exits, and review. A disciplined trader prepares responses before emotions appear.', 'deep_dive': [('Fear', 'Fear makes traders skip valid setups, close winners too early, or move stops too tight. The solution is predefined risk and rehearsal.'), ('Greed', 'Greed appears after wins or fast movement. It causes oversized trades and targets with no logical liquidity.'), ('Revenge', 'Revenge trading tries to force the market to give money back. It is one of the fastest ways to turn a small loss into a bad day.'), ('Overconfidence', 'After a winning streak, traders can mistake market conditions for personal skill. This is when daily limits and fixed risk are most important.'), ('Rule-based recovery', 'After a mistake: stop, log the rule break, reduce size next session, and review screenshots. Do not try to emotionally repair the account.')], 'process': ['Define emotional triggers', 'Set daily lockout', 'Use checklist before entry', 'Log mood', 'Review rule breaks weekly'], 'mistakes': ['Trading to feel better', 'Changing risk after wins', 'Deleting bad trades', 'Ignoring fatigue'], 'drill': 'Create a personal emergency rule: after two rule breaks or -2R, what exactly happens next? Write it and follow it for 30 days.'}, {'id': 'trade-management', 'track': 'Execution', 'title': 'Trade Management: Break Even, Partials, Runners, Trailing, and Exit Quality', 'level': 'Intermediate', 'time': '90 min', 'outcome': 'Manage winners and losers without letting P/L pressure destroy the original plan.', 'overview': 'Entry is only one part of trading. Management determines whether a good entry becomes a good trade. This course teaches when to reduce risk, take partials, hold runners, or exit early based on structure, not fear.', 'deep_dive': [('Break even', 'Moving to break even too early can stop out a valid trade. Move risk only after the market gives structure-based reason, such as a new swing or partial target hit.'), ('Partials', 'Partials convert open risk into realized progress. Use them at logical liquidity targets, profile levels, or 1R/2R points depending on the strategy.'), ('Runners', 'A runner is earned after risk is reduced. It should have a trailing or invalidation rule, not unlimited hope.'), ('Early exit', 'Exit early only if the trade idea changes: failed displacement, reclaim against bias, news risk, or clear rejection from target.'), ('Exit review', 'Judge exits by process quality. Did the exit follow your rule? Did it improve expectancy over a sample?')], 'process': ['Define partial zones', 'Define BE rule', 'Define runner rule', 'Define early-exit conditions', 'Log exit quality'], 'mistakes': ['Taking profit randomly', 'Moving stop too fast', 'Letting runner become red', 'Closing only from fear'], 'drill': 'Take your last five winners and mark whether your exit followed a planned rule or an emotional reaction.'}, {'id': 'range-trading', 'track': 'Strategies', 'title': 'Range Trading: Value Edges, Liquidity Sweeps, Midline, and Breakout Failure', 'level': 'Intermediate', 'time': '85 min', 'outcome': 'Trade ranges with rules instead of buying/selling every bounce.', 'overview': 'A range is an auction stuck between accepted boundaries. The highest-quality range trades usually happen at edges after liquidity events, not in the middle. This course teaches edge-to-edge logic and when to stop fading the range.', 'deep_dive': [('Range anatomy', 'A range has upper liquidity, lower liquidity, internal midpoint, and often a POC near the fairest price. The middle is usually lower quality.'), ('Sweep at edge', 'A sweep beyond range high/low followed by rejection can offer a reversal trade back toward POC or the opposite side.'), ('Acceptance outside range', 'If price closes and holds outside the range, fading it becomes dangerous. Acceptance can turn the range edge into support/resistance.'), ('Volume profile in ranges', 'POC often acts as a magnet. VAH/VAL can define the edges of accepted value. LVNs can create fast travel zones.'), ('Breakout failure', 'If price breaks out and immediately reclaims the range, trapped traders can fuel a move back through value.')], 'process': ['Mark range high/low', 'Mark POC/midline', 'Avoid middle entries', 'Wait for sweep/rejection or acceptance', 'Target POC/opposite edge'], 'mistakes': ['Trading every touch', 'Ignoring breakout acceptance', 'Entering mid-range', 'No invalidation outside edge'], 'drill': 'Find three range days and label: high, low, midpoint, POC, best sweep, and where fading became invalid.'}, {'id': 'trend-continuation', 'track': 'Strategies', 'title': 'Trend Continuation: Pullbacks, FVGs, Order Blocks, Flags, and Measured Moves', 'level': 'Intermediate', 'time': '90 min', 'outcome': 'Trade with trend after confirmation instead of chasing the extension candle.', 'overview': 'Trend continuation works best when the trader waits for pullback into a logical zone after displacement. The goal is not to buy the high or sell the low, but to join continuation at a defended level.', 'deep_dive': [('Impulse then pullback', 'A trend move needs an impulse that breaks structure. The pullback gives a risk-defined entry if it respects FVG, order block, trendline, or profile level.'), ('Flags and pennants', 'Small consolidations after a sharp move can continue, but only if breakout direction, volume/participation, and context support it.'), ('Order blocks', 'Use the last opposing candle before displacement as a decision zone only when it aligns with structure and liquidity.'), ('Measured moves', 'Targets can be projected from prior impulse legs, but should be checked against liquidity and profile levels.')], 'process': ['Confirm trend', 'Wait for displacement', 'Mark pullback zone', 'Enter after confirmation', 'Target next liquidity/measured move'], 'mistakes': ['Chasing extended candles', 'Buying into resistance', 'Ignoring pullback quality', 'Holding after structure breaks'], 'drill': 'Replay one trend day and identify the first safe pullback entry after displacement instead of the first impulse candle.'}, {'id': 'reversal-playbook', 'track': 'Strategies', 'title': 'Reversal Playbook: Exhaustion, Sweep, CHoCH, Profile Rejection, and Confirmation', 'level': 'Advanced', 'time': '95 min', 'outcome': 'Trade reversals only after evidence, not because price feels too high or low.', 'overview': 'Reversals are attractive but dangerous. A professional reversal trade needs location, liquidity sweep, exhaustion or absorption, structure shift, and a risk-defined retest. The goal is to stop picking tops/bottoms blindly.', 'deep_dive': [('Location', 'Reversals matter more at previous highs/lows, VAH/VAL, weekly levels, major supply/demand, or post-news extremes.'), ('Exhaustion', 'Extended candles into a target can show urgency, but exhaustion is confirmed only when follow-through fails.'), ('CHoCH', 'Change of character is early evidence, not final proof. It should be followed by retest, lower-timeframe confirmation, or profile reclaim/rejection.'), ('Profile rejection', 'A failed auction above VAH or below VAL can support reversal back into value. Holding outside value cancels the fade idea.'), ('Risk', 'Reversal stops often belong beyond the sweep extreme or invalidation structure, not at random small distances.')], 'process': ['Find major location', 'Wait for sweep/exhaustion', 'Confirm CHoCH/displacement', 'Enter retest', 'Stop beyond sweep', 'Target POC/opposite liquidity'], 'mistakes': ['Shorting because price is high', 'Buying because price is low', 'Ignoring trend strength', 'Entering before CHoCH'], 'drill': 'Find two failed reversal attempts and two successful reversals. Write the difference in location, confirmation, and stop placement.'}, {'id': 'backtesting-forward-testing', 'track': 'Review', 'title': 'Backtesting, Forward Testing, and Building a Real Edge', 'level': 'All levels', 'time': '100 min', 'outcome': 'Turn learning into measurable strategy development.', 'overview': 'A trader cannot know if a setup works from memory or emotion. Backtesting builds familiarity; forward testing tests execution; live trading with small risk tests psychology. All three are needed before scaling.', 'deep_dive': [('Backtesting', 'Use historical charts to define setup frequency, win rate, average R, drawdown, and best sessions. Do not curve-fit perfect examples only.'), ('Forward testing', 'Forward testing reveals whether the setup can be recognized live without hindsight. This is where many vague rules break.'), ('Sample size', 'A few trades mean little. Start with 20 examples for learning, 50 for early confidence, and 100+ for stronger evidence.'), ('Metrics', 'Track win rate, average win, average loss, expectancy, max drawdown, time of day, setup tag, and rule breaks.'), ('Scaling', 'Scale only after the strategy and behavior both show stability. More size cannot fix a broken process.')], 'process': ['Define setup', 'Collect screenshots', 'Log 50 examples', 'Forward test 20 sessions', 'Review expectancy', 'Scale slowly'], 'mistakes': ['Only saving winners', 'Changing rules during test', 'No sample size', 'Scaling before proof'], 'drill': 'Create a spreadsheet with 30 historical examples of one setup. Record R result and whether the rules were fully present.'}, {'id': 'broker-platform-mt5', 'track': 'Operations', 'title': 'Broker, MT5, Spread, Slippage, Sessions, and Execution Operations', 'level': 'Beginner → Intermediate', 'time': '70 min', 'outcome': 'Understand operational risks that can break a good trading plan.', 'overview': 'Trading execution depends on more than analysis. Broker server, symbol specs, spread, slippage, contract size, margin, swap, session times, and platform stability can all affect results. Users need operational literacy before live trading.', 'deep_dive': [('Broker server and account type', 'Demo and live accounts can use different servers and symbols. Always verify the exact server, login, symbol visibility, and trading permission.'), ('Spread', 'Spread is part of cost. Around rollover, news, or low liquidity, spread can widen and make tight stops unrealistic.'), ('Slippage', 'Fast markets can fill at worse prices. Plan for slippage around news and during low-liquidity periods.'), ('Contract specs', 'Tick value, contract size, minimum lot, margin, and stop level rules affect position sizing and risk.'), ('Platform routine', 'Before trading: check connection, symbol visible, algo permissions if needed, account mode, news time, and risk settings.')], 'process': ['Verify account mode', 'Check symbol specs', 'Check spread', 'Check news calendar', 'Confirm risk settings', 'Log execution issues'], 'mistakes': ['Using demo settings on live', 'Ignoring spread', 'Trading during platform instability', 'Wrong symbol contract assumptions'], 'drill': 'Open your broker symbol specification for XAUUSD and record contract size, tick value, min lot, spread behavior, and margin requirement.'}])
QUIZ_BANK.extend([{'id': 'q101', 'track': 'Market History', 'question': 'Why can USD strength pressure XAUUSD?', 'options': ['Because gold is globally quoted in USD', 'Because gold has no chart', 'Because spreads disappear', 'Because candles stop forming'], 'answer': 'Because gold is globally quoted in USD', 'explain': 'When USD strengthens, gold can become more expensive for non-dollar buyers and may face pressure, although structure still decides entries.'}, {'id': 'q102', 'track': 'Market History', 'question': 'What should a trader do with macro history?', 'options': ['Use it as bias awareness, not an entry trigger', 'Enter every headline immediately', 'Ignore risk', 'Trade without stops'], 'answer': 'Use it as bias awareness, not an entry trigger', 'explain': 'Macro background helps context, but execution still needs structure, liquidity, confirmation, and risk.'}, {'id': 'q103', 'track': 'Order Flow', 'question': 'What does fast tape usually suggest?', 'options': ['Momentum or urgency', 'A guaranteed reversal', 'No market activity', 'A perfect stop location'], 'answer': 'Momentum or urgency', 'explain': 'Fast prints often show urgency, but they must be interpreted at a key level with price response.'}, {'id': 'q104', 'track': 'Order Flow', 'question': 'If aggressive buying cannot lift price at resistance, what may be happening?', 'options': ['Absorption or hidden selling', 'The market is closed', 'Risk is removed', 'The candle is always bullish'], 'answer': 'Absorption or hidden selling', 'explain': 'Strong buying that fails to advance can mean a larger seller is absorbing demand.'}, {'id': 'q105', 'track': 'Market Profile', 'question': 'What is a Low Volume Node often associated with?', 'options': ['A thin area where price can move quickly', 'The highest traded price', 'A broker password', 'A guaranteed support'], 'answer': 'A thin area where price can move quickly', 'explain': 'LVNs show areas with less traded volume, so price may travel through them faster.'}, {'id': 'q106', 'track': 'Market Profile', 'question': 'What does acceptance above VAH suggest?', 'options': ['Buyers may be accepting higher value', 'Price must instantly crash', 'The broker changed leverage', 'The session is over'], 'answer': 'Buyers may be accepting higher value', 'explain': 'Holding above VAH can show acceptance beyond prior value; falling back inside can show rejection.'}, {'id': 'q107', 'track': 'Execution', 'question': 'What is the job of the 1M chart?', 'options': ['Entry refinement after higher context', 'Replace all charts', 'Set weekly macro bias', 'Predict FOMC'], 'answer': 'Entry refinement after higher context', 'explain': 'The 1M is a trigger/refinement chart and should not override higher timeframe context.'}, {'id': 'q108', 'track': 'Execution', 'question': 'What is the danger of moving to breakeven too early?', 'options': ['Stopping out a valid trade before structure develops', 'Making the broker vanish', 'Increasing target certainty', 'Removing all commissions'], 'answer': 'Stopping out a valid trade before structure develops', 'explain': 'Breakeven movement should be tied to structure or partial targets, not fear.'}, {'id': 'q109', 'track': 'SPX / Indices', 'question': 'Why do index options require spread/liquidity checks?', 'options': ['The chart can be right but the contract execution can be poor', 'Spreads are always zero', 'Contracts never move', 'Stops do not matter'], 'answer': 'The chart can be right but the contract execution can be poor', 'explain': 'A wide spread or illiquid contract can ruin a good chart idea.'}, {'id': 'q110', 'track': 'SPX / Indices', 'question': 'What should happen if an options stop condition is hit?', 'options': ['Exit and cancel remaining target orders', 'Marry the play', 'Add risk automatically', 'Ignore the plan'], 'answer': 'Exit and cancel remaining target orders', 'explain': 'The trade idea is invalid when stop conditions hit; target orders should not remain active by accident.'}, {'id': 'q111', 'track': 'Price Action', 'question': 'Why are chart pattern statistics not guarantees?', 'options': ['Execution, regime, risk, and context change outcomes', 'Patterns never exist', 'Charts have no history', 'Stops are illegal'], 'answer': 'Execution, regime, risk, and context change outcomes', 'explain': 'Statistics help compare patterns but do not guarantee any individual trade.'}, {'id': 'q112', 'track': 'Price Action', 'question': 'What is a failed breakout often useful for?', 'options': ['A possible opposite-direction setup', 'Proof that stops are useless', 'Random lot sizing', 'Deleting the chart'], 'answer': 'A possible opposite-direction setup', 'explain': 'Failed breakouts can trap traders and fuel moves back through the range/value.'}, {'id': 'q113', 'track': 'Technical Analysis', 'question': 'What should Fibonacci levels be used with?', 'options': ['Structure and confirmation', 'Blind entries only', 'No stop', 'Random news'], 'answer': 'Structure and confirmation', 'explain': 'Fibonacci is a planning tool, not an entry by itself.'}, {'id': 'q114', 'track': 'Technical Analysis', 'question': 'What is the purpose of a protective stop?', 'options': ['Define risk and invalidation', 'Guarantee profit', 'Increase emotions', 'Replace analysis'], 'answer': 'Define risk and invalidation', 'explain': 'Protective stops are risk tools aligned with the setup and account plan.'}, {'id': 'q115', 'track': 'Playbook Building', 'question': 'What is the difference between setup and entry?', 'options': ['Setup is condition; entry is trigger', 'They are identical', 'Entry is always bigger size', 'Setup means no risk'], 'answer': 'Setup is condition; entry is trigger', 'explain': 'The setup describes the environment; the entry is the exact execution trigger.'}, {'id': 'q116', 'track': 'Playbook Building', 'question': 'Why should a playbook include no-trade filters?', 'options': ['To stop trading in low-quality conditions', 'To avoid all learning', 'To increase random trades', 'To hide losses'], 'answer': 'To stop trading in low-quality conditions', 'explain': 'Filters protect the edge from bad sessions, news, chop, or emotional states.'}, {'id': 'q117', 'track': 'XAUUSD', 'question': 'Why wait after major news?', 'options': ['First spikes can be emotional and spreads can widen', 'News removes slippage', 'Gold stops moving', 'POC disappears'], 'answer': 'First spikes can be emotional and spreads can widen', 'explain': 'Post-news structure is usually safer than guessing the first candle.'}, {'id': 'q118', 'track': 'Mindset', 'question': 'What is revenge trading?', 'options': ['Trying to force the market to give money back', 'Following a written plan', 'Taking a valid loss', 'Reducing size'], 'answer': 'Trying to force the market to give money back', 'explain': 'Revenge trading is emotional recovery behavior that often worsens drawdown.'}, {'id': 'q119', 'track': 'Review', 'question': 'Why is sample size important?', 'options': ['A few trades do not prove an edge', 'It makes stops useless', 'It guarantees winning', 'It replaces journaling'], 'answer': 'A few trades do not prove an edge', 'explain': 'A strategy needs enough examples to judge win rate, average R, and drawdown.'}, {'id': 'q120', 'track': 'Operations', 'question': 'What should be checked before live MT5 trading?', 'options': ['Account mode, symbol specs, spread, news, and risk settings', 'Only candle color', 'Only page title', 'Nothing on demo'], 'answer': 'Account mode, symbol specs, spread, news, and risk settings', 'explain': 'Execution operations can break a good plan if account mode, spread, contract specs, or risk controls are wrong.'}])

# Helpful endpoints for future integrations, imports, or admin sync jobs.
def get_default_education_courses() -> list[dict[str, Any]]:
    return list(COURSE_LIBRARY)

def get_default_quiz_bank() -> list[dict[str, Any]]:
    return list(QUIZ_BANK)

def get_education_data_endpoints() -> dict[str, str]:
    return {
        'sqlite_db': str(DB_PATH),
        'settings_table': 'education_settings',
        'custom_courses_table': 'custom_courses',
        'zoom_classes_table': 'zoom_classes',
        'videos_table': 'education_videos',
        'css_path': str(STYLE_PATH),
    }

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


def _course_search_blob(course: dict[str, Any]) -> str:
    parts: list[str] = [str(course.get('title','')), str(course.get('overview','')), str(course.get('track','')), str(course.get('outcome',''))]
    for item in course.get('deep_dive', []) or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            parts.extend([str(item[0]), str(item[1])])
        else:
            parts.append(str(item))
    for key in ('process', 'mistakes'):
        value = course.get(key, [])
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        else:
            parts.append(str(value))
    parts.append(str(course.get('drill','')))
    return ' '.join(parts).lower()

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
    st.markdown('<div class="edu-path-map"><b>Production curriculum map:</b> Foundation → Market History → Technical Analysis → Market Profile → Order Flow → SMC → SPX/Indices → XAUUSD Macro → Execution → Mindset → Review → Operations. CEO custom courses appear in the same flow for all users.</div>', unsafe_allow_html=True)
    left, right = st.columns([1.2, 2])
    with left:
        track = st.selectbox("Course track", _track_options(courses), key="edu_course_track")
    with right:
        search = st.text_input("Search lessons", placeholder="Example: volume profile, timeframe, FVG, risk...", key="edu_course_search")
    filtered = [c for c in courses if track == "All" or c.get("track") == track]
    if search.strip():
        s = search.lower().strip()
        filtered = [c for c in filtered if s in _course_search_blob(c)]
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
