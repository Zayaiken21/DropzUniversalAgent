from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import html
import sqlite3
import uuid

import pandas as pd
import streamlit as st

try:
    from news_endpoints import get_gold_news_dashboard
except Exception:
    get_gold_news_dashboard = None

DB_PATH = Path("data/tradesmart_tools.db")
DEFAULT_TZ = "America/New_York"

SESSION_DEFS = [
    {"name":"Sydney","open":22.0,"close":7.0,"color":"#00d4ff","note":"Early liquidity. Often smoother movement; good for seeing if Asia builds a range.","play":"Mark Asian high/low. Avoid forcing trades if range is tight."},
    {"name":"Tokyo","open":0.0,"close":9.0,"color":"#ffca28","note":"Asian range can create liquidity for London and New York to sweep.","play":"Watch if price traps one side of the range before expansion."},
    {"name":"London","open":8.0,"close":17.0,"color":"#2979ff","note":"Expansion window. Strong for stop hunts, displacement, and trend continuation.","play":"Look for sweep → displacement → retrace entries around FVG/OB."},
    {"name":"New York","open":13.0,"close":22.0,"color":"#00e676","note":"Major XAUUSD window, especially near USD news and Wall Street open.","play":"Respect news. Confirm dollar/yield reaction before chasing gold."},
]

TIMEZONE_OPTIONS = {
    "New York / EST-EDT": "America/New_York",
    "London": "Europe/London",
    "Tokyo": "Asia/Tokyo",
    "Sydney": "Australia/Sydney",
    "UTC": "UTC",
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--ts-bg:#0a0e1a;--ts-card:#0f1629;--ts-card2:#131d38;--ts-card3:#101a33;--ts-edge:#1c2845;--ts-blue:#1e6fff;--ts-glow:#4d8fff;--ts-cyan:#00d4ff;--ts-green:#00e676;--ts-red:#ff3d5a;--ts-gold:#ffca28;--ts-purple:#9b5cff;--ts-text:#b8cef0;--ts-dim:#576b99;--ts-hud:'Orbitron',monospace;--ts-mono:'JetBrains Mono',monospace}
.ts-hero{position:relative;overflow:hidden;background:radial-gradient(circle at 20% 20%,#1e6fff55,transparent 28%),radial-gradient(circle at 80% 10%,#00d4ff35,transparent 22%),linear-gradient(135deg,#0f1629,#0a0e1a);border:1px solid var(--ts-edge);border-radius:18px;padding:22px 24px;margin-bottom:18px;box-shadow:0 0 28px #1e6fff18}.ts-hero h1{font-family:var(--ts-hud);font-size:1.55rem;margin:0;color:#eaf4ff;letter-spacing:.04em}.ts-hero p{font-family:var(--ts-mono);font-size:.76rem;color:var(--ts-dim);margin:8px 0 0}.ts-orb{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--ts-cyan);box-shadow:0 0 14px var(--ts-cyan);margin-right:8px}
/* only style the content tabs, not your app/sidebar menu */
div[data-testid="stTabs"]>div:first-child{border-bottom:1px solid var(--ts-edge)!important;gap:3px!important;flex-wrap:wrap!important}button[data-testid="stTab"]{font-family:var(--ts-hud)!important;font-size:.58rem!important;font-weight:800!important;letter-spacing:.08em!important;color:var(--ts-dim)!important;border-radius:10px 10px 0 0!important;padding:9px 13px!important;border:1px solid transparent!important;border-bottom:none!important;background:transparent!important}button[data-testid="stTab"]:hover{color:var(--ts-cyan)!important}button[data-testid="stTab"][aria-selected="true"]{color:var(--ts-cyan)!important;border-color:var(--ts-edge)!important;background:linear-gradient(180deg,var(--ts-card2),var(--ts-card))!important;box-shadow:0 -8px 22px #1e6fff18!important}
/* dark inputs/dropdowns/date fields so text never disappears */
div[data-testid="stNumberInput"] input,div[data-testid="stTextInput"] input,div[data-testid="stTextArea"] textarea,div[data-testid="stDateInput"] input{background:var(--ts-bg)!important;border:1px solid var(--ts-edge)!important;color:var(--ts-text)!important;font-family:var(--ts-mono)!important;font-size:.82rem!important;border-radius:7px!important}div[data-baseweb="select"]>div,div[data-baseweb="select"] div{background-color:var(--ts-bg)!important;color:var(--ts-text)!important;border-color:var(--ts-edge)!important}div[data-baseweb="popover"],ul[role="listbox"],li[role="option"]{background:var(--ts-card)!important;color:var(--ts-text)!important}li[role="option"]:hover{background:#1c2845!important}label[data-testid="stWidgetLabel"] p{font-family:var(--ts-mono)!important;font-size:.70rem!important;color:var(--ts-dim)!important;letter-spacing:.03em!important}div[data-testid="stButton"]>button,div[data-testid="stDownloadButton"]>button{background:linear-gradient(135deg,#1a5fe8,#2979ff)!important;color:#fff!important;font-family:var(--ts-hud)!important;font-size:.60rem!important;font-weight:800!important;letter-spacing:.13em!important;border:none!important;border-radius:7px!important;padding:10px 0!important;width:100%!important}div[data-testid="stButton"]>button:hover,div[data-testid="stDownloadButton"]>button:hover{filter:brightness(1.18)!important;box-shadow:0 0 18px #1e6fff45!important}
div[data-testid="stMetric"]{background:linear-gradient(180deg,var(--ts-card2),var(--ts-card3))!important;border:1px solid var(--ts-edge)!important;border-radius:12px!important;padding:15px 16px!important;box-shadow:0 0 20px #00000022!important}div[data-testid="stMetricLabel"] p{font-family:var(--ts-mono)!important;font-size:.62rem!important;color:var(--ts-dim)!important;letter-spacing:.08em!important}div[data-testid="stMetricValue"]{font-family:var(--ts-hud)!important;font-size:1.18rem!important;color:var(--ts-cyan)!important}.ts-panel{background:linear-gradient(180deg,#131d38,#0f1629);border:1px solid var(--ts-edge);border-radius:14px;padding:16px 18px;margin-top:14px;font-family:var(--ts-mono);font-size:.78rem;box-shadow:0 0 26px #00000022}.ts-eyebrow{font-family:var(--ts-hud);font-size:.58rem;font-weight:900;letter-spacing:.18em;color:var(--ts-blue);text-transform:uppercase;margin:4px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--ts-edge)}.ts-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #151f3a}.ts-row:last-child{border-bottom:none}.ts-label{color:var(--ts-dim);font-size:.70rem}.ts-val{font-weight:700;color:var(--ts-text);text-align:right}.ts-green{color:var(--ts-green)!important}.ts-red{color:var(--ts-red)!important}.ts-gold{color:var(--ts-gold)!important}.ts-cyan{color:var(--ts-cyan)!important}.ts-blue{color:var(--ts-glow)!important}.ts-purple{color:var(--ts-purple)!important}.ts-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.ts-mini{background:#0a0e1a;border:1px solid var(--ts-edge);border-radius:12px;padding:12px}.ts-mini b{font-family:var(--ts-hud);font-size:.65rem;color:var(--ts-text)}.ts-mini span{display:block;font-family:var(--ts-mono);font-size:.62rem;color:var(--ts-dim);margin-top:5px;line-height:1.45}.ts-chip{display:inline-block;padding:3px 10px;border-radius:999px;font-family:var(--ts-mono);font-size:.64rem;font-weight:800;margin:3px 3px 0}.ts-chip-green{background:#00e67618;color:var(--ts-green);border:1px solid #00e67640}.ts-chip-red{background:#ff3d5a18;color:var(--ts-red);border:1px solid #ff3d5a40}.ts-chip-gold{background:#ffca2818;color:var(--ts-gold);border:1px solid #ffca2840}.ts-chip-cyan{background:#00d4ff18;color:var(--ts-cyan);border:1px solid #00d4ff40}.ts-chip-purple{background:#9b5cff18;color:var(--ts-purple);border:1px solid #9b5cff40}.ts-table{width:100%;border-collapse:collapse;font-family:var(--ts-mono);font-size:.74rem;margin-top:10px}.ts-table th{color:var(--ts-dim);font-size:.61rem;letter-spacing:.07em;font-weight:500;text-align:left;padding:5px 8px 7px;border-bottom:1px solid var(--ts-edge)}.ts-table td{padding:7px 8px;border-bottom:1px solid #141d36;color:var(--ts-text);vertical-align:top}.ts-session-card{position:relative;border:1px solid var(--ts-edge);background:#0a0e1a;border-radius:14px;padding:14px;margin:10px 0;overflow:hidden}.ts-session-card.active{border-color:#00d4ff80;box-shadow:0 0 22px #00d4ff22}.ts-session-card.overlap{border-color:#ffca28aa;box-shadow:0 0 28px #ffca2830}.ts-session-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.ts-dot{width:11px;height:11px;border-radius:50%;display:inline-block;margin-right:8px}.ts-timeline{position:relative;height:13px;border:1px solid var(--ts-edge);border-radius:999px;background:#050813;margin-top:11px;overflow:hidden}.ts-fill{position:absolute;height:100%;border-radius:999px;opacity:.86}.ts-now{position:absolute;top:-2px;width:2px;height:17px;background:#fff;box-shadow:0 0 8px #fff}.ts-note{font-family:var(--ts-mono);font-size:.70rem;color:var(--ts-dim);line-height:1.5}.ts-action{font-family:var(--ts-hud);font-size:.62rem;letter-spacing:.09em}.ts-time-line{display:flex;justify-content:space-between;font-family:var(--ts-mono);font-size:.62rem;color:var(--ts-dim);margin-top:5px}.ts-news-card{background:#0a0e1a;border:1px solid var(--ts-edge);border-radius:13px;padding:13px;margin:10px 0}.ts-news-card.high{border-color:#ff3d5a66}.ts-news-title{font-family:var(--ts-hud);font-size:.74rem;color:var(--ts-text);line-height:1.4}.ts-news-meta{font-family:var(--ts-mono);font-size:.62rem;color:var(--ts-dim);margin-top:6px}.ts-danger-zone{border:1px solid #ff3d5a44;background:#ff3d5a10;border-radius:12px;padding:12px;margin-top:12px}@media(max-width:900px){.ts-grid{grid-template-columns:repeat(2,1fr)}.ts-hero h1{font-size:1.2rem}button[data-testid="stTab"]{font-size:.53rem!important;padding:8px 9px!important}}@media(max-width:520px){.ts-grid{grid-template-columns:1fr}.ts-row{align-items:flex-start;gap:8px}.ts-val{text-align:right}}
</style>
"""


def _safe_user_id(role: str) -> str:
    user = st.session_state.get("user") or {}
    return str(user.get("id") or user.get("username") or user.get("email") or role or "guest")


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS user_tool_settings(user_id TEXT PRIMARY KEY, timezone TEXT NOT NULL DEFAULT 'America/New_York', updated_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS trade_journal(
            id TEXT PRIMARY KEY,user_id TEXT NOT NULL,trade_date TEXT NOT NULL,symbol TEXT NOT NULL,session_name TEXT NOT NULL,
            direction TEXT NOT NULL,setup TEXT,entry REAL NOT NULL,stop REAL,target REAL,exit REAL,lots REAL NOT NULL,
            result TEXT NOT NULL,pnl REAL NOT NULL,r_multiple REAL,mood TEXT,mistake TEXT,notes TEXT,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        # Migration safety for older dev DBs. Also repairs rows that were created before NOT NULL timestamps existed.
        cols = {r[1] for r in con.execute("PRAGMA table_info(trade_journal)").fetchall()}
        for name in ["created_at", "updated_at"]:
            if name not in cols:
                con.execute(f"ALTER TABLE trade_journal ADD COLUMN {name} TEXT")
        now = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE trade_journal SET created_at=COALESCE(created_at, ?) WHERE created_at IS NULL OR created_at=''", (now,))
        con.execute("UPDATE trade_journal SET updated_at=COALESCE(updated_at, ?) WHERE updated_at IS NULL OR updated_at=''", (now,))
        con.commit()


def _get_user_tz(user_id: str) -> str:
    _init_db()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT timezone FROM user_tool_settings WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else DEFAULT_TZ


def _save_user_tz(user_id: str, tz: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""INSERT INTO user_tool_settings(user_id,timezone,updated_at) VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET timezone=excluded.timezone,updated_at=excluded.updated_at""", (user_id, tz, now))
        con.commit()


def _load_trades(user_id: str) -> pd.DataFrame:
    _init_db()
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("SELECT * FROM trade_journal WHERE user_id=? ORDER BY trade_date DESC, created_at DESC", con, params=(user_id,))


def _save_trade(user_id: str, row: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    tid = row.get("id") or uuid.uuid4().hex
    created_at = row.get("created_at") or now
    values = {**row, "id": tid, "user_id": user_id, "created_at": created_at, "updated_at": now}
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""INSERT INTO trade_journal(id,user_id,trade_date,symbol,session_name,direction,setup,entry,stop,target,exit,lots,result,pnl,r_multiple,mood,mistake,notes,created_at,updated_at)
        VALUES(:id,:user_id,:trade_date,:symbol,:session_name,:direction,:setup,:entry,:stop,:target,:exit,:lots,:result,:pnl,:r_multiple,:mood,:mistake,:notes,:created_at,:updated_at)
        ON CONFLICT(id) DO UPDATE SET trade_date=excluded.trade_date,symbol=excluded.symbol,session_name=excluded.session_name,direction=excluded.direction,setup=excluded.setup,entry=excluded.entry,stop=excluded.stop,target=excluded.target,exit=excluded.exit,lots=excluded.lots,result=excluded.result,pnl=excluded.pnl,r_multiple=excluded.r_multiple,mood=excluded.mood,mistake=excluded.mistake,notes=excluded.notes,updated_at=excluded.updated_at""", values)
        con.commit()


def _delete_trade(user_id: str, tid: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM trade_journal WHERE user_id=? AND id=?", (user_id, tid))
        con.commit()


def _clear_trades(user_id: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM trade_journal WHERE user_id=?", (user_id,))
        con.commit()


def _panel(rows: list[tuple[str, str, str]]) -> str:
    return '<div class="ts-panel">' + ''.join(f'<div class="ts-row"><span class="ts-label">{html.escape(label)}</span><span class="ts-val {cls}">{html.escape(str(value))}</span></div>' for label, value, cls in rows) + '</div>'


def _fmt_mins(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _clock_label(hour_float: float, tz_name: str) -> str:
    base = datetime(2026, 1, 1, int(hour_float), int((hour_float % 1) * 60), tzinfo=timezone.utc)
    return base.astimezone(ZoneInfo(tz_name)).strftime("%I:%M %p %Z")


def _session_info(tz_name: str) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    h = now_utc.hour + now_utc.minute / 60
    out = []
    for s in SESSION_DEFS:
        o, c = s["open"], s["close"]
        active = (h >= o or h < c) if o > c else (o <= h < c)
        out.append({
            **s,
            "active": active,
            "mins_left": int(((c - h) % 24) * 60),
            "mins_to": int(((o - h) % 24) * 60),
            "start_local": _clock_label(o, tz_name),
            "end_local": _clock_label(c, tz_name),
            "start_ny": _clock_label(o, DEFAULT_TZ),
            "end_ny": _clock_label(c, DEFAULT_TZ),
        })
    return out


def _render_session_timeline(sessions: list[dict[str, Any]]) -> str:
    now_utc = datetime.now(timezone.utc)
    now_pct = ((now_utc.hour * 60 + now_utc.minute) / 1440) * 100
    active_names = [s["name"] for s in sessions if s["active"]]
    overlap = "London" in active_names and "New York" in active_names
    rows = ""
    for s in sessions:
        start = s["open"] / 24 * 100
        end = s["close"] / 24 * 100
        if s["open"] > s["close"]:
            fill = f'<span class="ts-fill" style="left:{start:.3f}%;width:{100-start:.3f}%;background:{s["color"]}"></span><span class="ts-fill" style="left:0;width:{end:.3f}%;background:{s["color"]}"></span>'
        else:
            fill = f'<span class="ts-fill" style="left:{start:.3f}%;width:{end-start:.3f}%;background:{s["color"]}"></span>'
        cls = "ts-session-card active" if s["active"] else "ts-session-card"
        if overlap and s["name"] in ("London", "New York"):
            cls += " overlap"
        status = f'OPEN · closes in {_fmt_mins(s["mins_left"])}' if s["active"] else f'closed · opens in {_fmt_mins(s["mins_to"])}'
        dot_shadow = f'box-shadow:0 0 13px {s["color"]}' if s["active"] else 'box-shadow:none;opacity:.38'
        rows += f'''
        <div class="{cls}">
          <div class="ts-session-head"><div><span class="ts-dot" style="background:{s['color']};{dot_shadow}"></span><b style="font-family:var(--ts-hud);color:var(--ts-text);font-size:.76rem">{s['name']}</b></div><span class="ts-action {'ts-green' if s['active'] else 'ts-blue'}">{status}</span></div>
          <div class="ts-time-line"><span>Local: {s['start_local']} → {s['end_local']}</span><span>NYC: {s['start_ny']} → {s['end_ny']}</span></div>
          <div class="ts-timeline">{fill}<span class="ts-now" style="left:{now_pct:.3f}%"></span></div>
          <div class="ts-note" style="margin-top:9px"><b style="color:var(--ts-text)">What it means:</b> {s['note']}<br><b style="color:var(--ts-text)">Possible logic:</b> {s['play']}</div>
        </div>'''
    return rows


def _tab_sessions(user_id: str) -> None:
    st.markdown('<div class="ts-eyebrow">Market Session Atlas</div>', unsafe_allow_html=True)
    current_tz = _get_user_tz(user_id)
    labels = list(TIMEZONE_OPTIONS.keys())
    reverse = {v: k for k, v in TIMEZONE_OPTIONS.items()}
    selected_label = st.selectbox("Display session times in", labels, index=labels.index(reverse.get(current_tz, "New York / EST-EDT")), key="tz_select")
    selected_tz = TIMEZONE_OPTIONS[selected_label]
    if selected_tz != current_tz:
        _save_user_tz(user_id, selected_tz)
        st.success(f"Session timezone saved for this user: {selected_label}")
    sessions = _session_info(selected_tz)
    now_local = datetime.now(ZoneInfo(selected_tz))
    now_ny = datetime.now(ZoneInfo(DEFAULT_TZ))
    active = [s["name"] for s in sessions if s["active"]]
    chips = ''.join(f'<span class="ts-chip ts-chip-green">{a} active</span>' for a in active) or '<span class="ts-chip ts-chip-red">No major session active</span>'
    if "London" in active and "New York" in active:
        chips += '<span class="ts-chip ts-chip-gold">⚡ London / NY overlap: strongest gold liquidity window</span>'
    st.markdown(f'<div class="ts-panel"><div class="ts-row"><span class="ts-label">Selected clock</span><span class="ts-val ts-cyan">{now_local.strftime("%I:%M:%S %p · %Z")}</span></div><div class="ts-row"><span class="ts-label">NYC / EST-EDT anchor</span><span class="ts-val ts-blue">{now_ny.strftime("%I:%M:%S %p · %Z")}</span></div><div style="margin-top:10px">{chips}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="ts-grid"><div class="ts-mini"><b>Asian Range</b><span>Builds liquidity. Mark highs/lows for London/NY sweeps.</span></div><div class="ts-mini"><b>London Expansion</b><span>Often starts the real direction or creates a fakeout.</span></div><div class="ts-mini"><b>NY News</b><span>USD news, yields, and DXY can move XAUUSD violently.</span></div><div class="ts-mini"><b>Overlap</b><span>London + NY active together usually means best volume.</span></div></div>', unsafe_allow_html=True)
    st.markdown(_render_session_timeline(sessions), unsafe_allow_html=True)


def _tab_journal(user_id: str) -> None:
    st.markdown('<div class="ts-eyebrow">Wired Trade Journal</div>', unsafe_allow_html=True)
    df = _load_trades(user_id)
    edit_options = ["New trade"] + (df.apply(lambda r: f'{r["trade_date"]} · {r["symbol"]} · {r["direction"]} · ${r["pnl"]:+.2f}', axis=1).tolist() if not df.empty else [])
    pick = st.selectbox("Journal action", edit_options, key="tj_pick")
    editing = pick != "New trade"
    edit_row = df.iloc[edit_options.index(pick) - 1].to_dict() if editing else {}
    setup_options = ["FVG", "Order Block", "Liquidity Sweep", "Breakout", "Reversal", "News", "Session Sweep", "Other"]
    mood_options = ["Focused", "Calm", "Rushed", "Fearful", "Greedy", "Tired"]
    with st.expander("➕ Add / Edit Trade", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        trade_date = c1.date_input("Date", value=date.fromisoformat(edit_row.get("trade_date", str(date.today()))), key="tj_date")
        symbol = c2.text_input("Symbol", value=edit_row.get("symbol", "XAUUSD"), key="tj_symbol")
        sessions = ["New York", "London", "London/NY Overlap", "Tokyo", "Sydney", "Other"]
        session_default = edit_row.get("session_name", "New York") if edit_row.get("session_name", "New York") in sessions else "Other"
        session_name = c3.selectbox("Session", sessions, index=sessions.index(session_default), key="tj_session")
        direction = c4.selectbox("Direction", ["Buy", "Sell"], index=0 if edit_row.get("direction", "Buy") == "Buy" else 1, key="tj_dir")
        p1, p2, p3, p4 = st.columns(4)
        entry = p1.number_input("Entry", value=float(edit_row.get("entry", 3300.0)), step=.01, format="%.2f", key="tj_entry")
        stop = p2.number_input("Stop", value=float(edit_row.get("stop", 3295.0) or 0), step=.01, format="%.2f", key="tj_stop")
        target = p3.number_input("Target", value=float(edit_row.get("target", 3315.0) or 0), step=.01, format="%.2f", key="tj_target")
        exit_p = p4.number_input("Exit", value=float(edit_row.get("exit", 3315.0) or 0), step=.01, format="%.2f", key="tj_exit")
        q1, q2, q3, q4 = st.columns(4)
        lots = q1.number_input("Lots", min_value=.01, value=float(edit_row.get("lots", .10)), step=.01, key="tj_lots")
        result = q2.selectbox("Result", ["Win", "Loss", "Breakeven"], index=["Win", "Loss", "Breakeven"].index(edit_row.get("result", "Win") if edit_row.get("result", "Win") in ["Win", "Loss", "Breakeven"] else "Win"), key="tj_result")
        setup_default = edit_row.get("setup", "Breakout") if edit_row.get("setup", "Breakout") in setup_options else "Other"
        setup = q3.selectbox("Setup", setup_options, index=setup_options.index(setup_default), key="tj_setup")
        mood_default = edit_row.get("mood", "Focused") if edit_row.get("mood", "Focused") in mood_options else "Focused"
        mood = q4.selectbox("Mood", mood_options, index=mood_options.index(mood_default), key="tj_mood")
        mistake = st.text_input("Mistake / Lesson", value=edit_row.get("mistake", ""), key="tj_mistake")
        notes = st.text_area("Notes", value=edit_row.get("notes", ""), placeholder="Setup, confluences, liquidity taken, session behavior, execution notes…", height=76, key="tj_notes")
        move = (exit_p - entry) if direction == "Buy" else (entry - exit_p)
        pnl = move * lots * 100
        risk_pts = abs(entry - stop) if stop else 0
        r_multiple = (move / risk_pts) if risk_pts else 0
        st.markdown(_panel([("Calculated P/L", f"${pnl:+,.2f}", "ts-green" if pnl >= 0 else "ts-red"), ("R Multiple", f"{r_multiple:+.2f}R", "ts-green" if r_multiple >= 0 else "ts-red")]), unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        if s1.button("SAVE TRADE", key="tj_save"):
            _save_trade(user_id, {"id": edit_row.get("id"), "trade_date": str(trade_date), "symbol": symbol.upper().strip() or "XAUUSD", "session_name": session_name, "direction": direction, "setup": setup, "entry": entry, "stop": stop, "target": target, "exit": exit_p, "lots": lots, "result": result, "pnl": round(pnl, 2), "r_multiple": round(r_multiple, 3), "mood": mood, "mistake": mistake, "notes": notes, "created_at": edit_row.get("created_at") or None})
            st.success("Trade saved to this user's journal database.")
            st.rerun()
        if editing and s2.button("DELETE SELECTED TRADE", key="tj_delete"):
            _delete_trade(user_id, edit_row["id"])
            st.success("Trade deleted.")
            st.rerun()
    df = _load_trades(user_id)
    if df.empty:
        st.markdown('<div class="ts-panel ts-note" style="text-align:center;padding:30px">No trades logged yet. Once saved, this journal stays stored per user in SQLite.</div>', unsafe_allow_html=True)
        return
    total = float(df["pnl"].sum()); wins = int((df["result"] == "Win").sum()); losses = int((df["result"] == "Loss").sum()); wr = wins / len(df) * 100 if len(df) else 0; avg_r = float(df["r_multiple"].fillna(0).mean())
    m1, m2, m3, m4 = st.columns(4); m1.metric("Total P/L", f"${total:+,.2f}"); m2.metric("Trades", str(len(df))); m3.metric("Win Rate", f"{wr:.0f}%"); m4.metric("Avg R", f"{avg_r:+.2f}R")
    show = df[["trade_date", "symbol", "session_name", "direction", "setup", "entry", "stop", "target", "exit", "lots", "result", "pnl", "r_multiple", "mood", "mistake", "notes"]].rename(columns={"trade_date":"Date", "session_name":"Session", "r_multiple":"R", "pnl":"P/L"})
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button("EXPORT JOURNAL CSV", show.to_csv(index=False).encode("utf-8"), file_name=f"tradesmart_journal_{user_id}.csv", mime="text/csv")
    with st.expander("Danger zone"):
        st.markdown('<div class="ts-danger-zone ts-note">This clears only the current logged-in user journal.</div>', unsafe_allow_html=True)
        if st.button("CLEAR MY JOURNAL", key="tj_clear"):
            _clear_trades(user_id); st.rerun()


def _tab_gold_news() -> None:
    st.markdown('<div class="ts-eyebrow">Gold News Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="ts-panel ts-note">Tracks gold drivers from yfinance, RSS, and a best-effort Forex Factory calendar scraper. Focus: XAUUSD, DXY/dollar, EURUSD pressure, yields, Fed news, CPI, PPI, NFP, and high-impact USD events.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    days = c1.selectbox("Calendar days", [1, 3, 7, 14], index=2, key="news_days")
    impact = c2.selectbox("Calendar impact", ["High", "Medium", "Low", "All"], key="news_impact")
    limit = c3.number_input("Headline limit", 5, 50, 20, 5, key="news_limit")
    keywords = st.text_input("News keywords", value="gold,xauusd,dxy,dollar,eurusd,fomc,cpi,nfp,fed,yields", key="news_keywords")
    use_yf = st.checkbox("Use yfinance market news", True, key="news_yf")
    use_rss = st.checkbox("Use RSS web news", True, key="news_rss")
    use_ff = st.checkbox("Scrape Forex Factory calendar", True, key="news_ff")
    if st.button("FETCH LIVE GOLD NEWS", key="news_fetch"):
        if get_gold_news_dashboard is None:
            st.error("news_endpoints.py must be in the same folder as tools_page.py. Also install the requirements below.")
            return
        data = get_gold_news_dashboard(keywords=[x.strip() for x in keywords.split(',') if x.strip()], limit=int(limit), include_yfinance=use_yf, include_rss=use_rss, include_forex_factory=use_ff, calendar_days=int(days), impact_filter=impact)
        st.markdown(f'<div class="ts-panel"><div class="ts-row"><span class="ts-label">Generated UTC</span><span class="ts-val ts-cyan">{html.escape(data.get("generated_at", ""))}</span></div><div class="ts-row"><span class="ts-label">Tracked yfinance symbols</span><span class="ts-val ts-blue">GC=F · GLD · DX-Y.NYB · UUP · EURUSD=X · ^TNX</span></div></div>', unsafe_allow_html=True)
        if data.get("errors"):
            st.warning("Some sources failed safely: " + " | ".join(data["errors"][:4]))
        calendar = data.get("calendar") or []
        if calendar:
            rows = "".join(f'<tr><td>{html.escape(e.get("date", ""))}</td><td>{html.escape(e.get("time", ""))}</td><td>{html.escape(e.get("currency", ""))}</td><td class="{"ts-red" if e.get("impact") == "High" else "ts-gold"}">{html.escape(e.get("impact", ""))}</td><td>{html.escape(e.get("event", ""))}<br><span class="ts-note">{html.escape(e.get("why_gold_cares", ""))}</span></td></tr>' for e in calendar[:60])
            st.markdown(f'<div class="ts-panel"><div class="ts-eyebrow">High Impact Calendar</div><table class="ts-table"><tr><th>Date</th><th>Time</th><th>Currency</th><th>Impact</th><th>Event / Gold Logic</th></tr>{rows}</table></div>', unsafe_allow_html=True)
        items = data.get("items") or []
        if items:
            cards = ""
            for item in items:
                imp = item.get("impact", "Low")
                cls = "high" if imp == "High" else ""
                title = html.escape(item.get("title", "Untitled")); url = html.escape(item.get("url", "#")); source = html.escape(item.get("source", "source")); provider = html.escape(item.get("provider", "")); pub = html.escape(item.get("published", "")); summary = html.escape(item.get("summary", "")); symbols = " · ".join(item.get("symbols") or [])
                cards += f'<div class="ts-news-card {cls}"><a class="ts-news-title" href="{url}" target="_blank" style="text-decoration:none">{title}</a><div class="ts-news-meta">{provider} · {source} · {pub} · Impact: {imp} · {html.escape(symbols)}</div><div class="ts-note" style="margin-top:7px">{summary}</div></div>'
            st.markdown(f'<div class="ts-panel"><div class="ts-eyebrow">Live Headlines</div>{cards}</div>', unsafe_allow_html=True)
        if not calendar and not items:
            st.info("No live items returned. Check internet access, install requirements, or disable the source that is blocked.")
    st.markdown('<div class="ts-panel ts-note"><b style="color:var(--ts-text)">Install:</b><br><code>pip install yfinance requests beautifulsoup4 lxml pandas</code><br><br><b style="color:var(--ts-text)">Note:</b> Forex Factory may block scraping or change its HTML. This script fails safely and still shows yfinance/RSS news.</div>', unsafe_allow_html=True)


def render_tools_page(role: str = "client") -> None:
    _init_db()
    user_id = _safe_user_id(role)
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="ts-hero"><h1><span class="ts-orb"></span>TradeSmart Tools</h1><p>Focused trading tools: session logic, per-user journal, and gold news intelligence.</p></div>', unsafe_allow_html=True)
    tabs = st.tabs(["🌐 Sessions", "📒 Journal", "📰 Gold News"])
    with tabs[0]: _tab_sessions(user_id)
    with tabs[1]: _tab_journal(user_id)
    with tabs[2]: _tab_gold_news()


def render_frontend_tools_page(role: str = "client"):
    render_tools_page(role)
    return None
