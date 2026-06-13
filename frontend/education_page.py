from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PAGE_CONFIG = {
    "name": "Education",
    "icon": "🎓",
    "roles": ["ceo", "client", "admin", "trader"],
}


LESSONS = [
    {
        "level": "Foundation",
        "title": "Market Structure",
        "time": "12 min",
        "focus": "Trend, range, swing highs/lows, BOS, CHoCH",
        "summary": "Learn how to read direction before looking for entries. Structure keeps you from chasing random candles.",
        "checklist": ["Mark the latest major high and low", "Decide trend or range", "Wait for confirmation before entry"],
    },
    {
        "level": "Foundation",
        "title": "Risk Before Reward",
        "time": "10 min",
        "focus": "Position sizing, max loss, daily guardrails",
        "summary": "A good setup can still lose. This lesson keeps risk controlled so one trade cannot damage the account.",
        "checklist": ["Risk 0.25%–1% while learning", "Know stop before entry", "Stop after max daily loss"],
    },
    {
        "level": "Smart Money",
        "title": "Liquidity Sweeps",
        "time": "15 min",
        "focus": "Equal highs/lows, stops, fakeouts, reversal confirmation",
        "summary": "Price often taps obvious liquidity before the real move. Learn how to wait for the sweep instead of becoming the liquidity.",
        "checklist": ["Find equal highs/lows", "Wait for sweep", "Confirm displacement away from sweep"],
    },
    {
        "level": "Smart Money",
        "title": "Fair Value Gaps",
        "time": "14 min",
        "focus": "Imbalance, displacement, pullback zones",
        "summary": "FVGs are not automatic entries. Learn which gaps matter and when price is likely to respect them.",
        "checklist": ["Only use FVG after displacement", "Prefer with trend/session bias", "Invalidation must be clear"],
    },
    {
        "level": "Execution",
        "title": "Session Timing",
        "time": "9 min",
        "focus": "Asia range, London expansion, New York news/open",
        "summary": "The same setup behaves differently by session. Learn when XAUUSD and indices usually have cleaner liquidity.",
        "checklist": ["Mark Asia high/low", "Respect London/NY overlap", "Avoid random dead-zone entries"],
    },
    {
        "level": "Execution",
        "title": "Entry Confirmation",
        "time": "16 min",
        "focus": "1M entry, 5M confirmation, candle close discipline",
        "summary": "Build a repeatable trigger process so your entries are based on confirmed behavior, not emotion.",
        "checklist": ["Use 5M for bias", "Use 1M for execution", "Do not enter before your trigger closes"],
    },
]

PLAYBOOKS = [
    {
        "name": "XAUUSD Sweep → Displacement → FVG",
        "best": "London or New York",
        "steps": "Mark liquidity → wait for sweep → confirm displacement → enter on FVG retrace → target opposite liquidity.",
        "avoid": "Entering directly into news candles or before displacement confirms.",
    },
    {
        "name": "NAS100 Range Break + Retest",
        "best": "NY open after volatility settles",
        "steps": "Mark premarket range → wait for close outside range → retest zone → enter with structure continuation.",
        "avoid": "Buying the first spike without a retest or stop location.",
    },
    {
        "name": "London/NY Continuation",
        "best": "8:00 AM–11:00 AM New York",
        "steps": "Use London direction → wait for NY pullback → confirm continuation candle → manage partials.",
        "avoid": "Fighting a strong trend because price feels too high or too low.",
    },
]

QUIZ = [
    {
        "question": "What should come first before planning an entry?",
        "options": ["A random candle color", "Market structure and risk", "A bigger lot size", "A social media signal"],
        "answer": "Market structure and risk",
    },
    {
        "question": "A liquidity sweep is strongest when it is followed by what?",
        "options": ["Immediate revenge entry", "Displacement away from the swept level", "Ignoring the stop", "Adding more risk"],
        "answer": "Displacement away from the swept level",
    },
    {
        "question": "Why use a trade log after each session?",
        "options": ["To prove every loss was unlucky", "To track repeatable behavior and mistakes", "To avoid backtesting", "To increase risk faster"],
        "answer": "To track repeatable behavior and mistakes",
    },
]


def _inject_education_css() -> None:
    st.markdown(
        """
        <style>
        .edu-hero{position:relative;overflow:hidden;padding:1.6rem;border-radius:26px;margin-bottom:1rem;background:radial-gradient(circle at 15% 15%,rgba(0,255,163,.22),transparent 30%),radial-gradient(circle at 88% 12%,rgba(255,202,40,.20),transparent 25%),linear-gradient(135deg,rgba(10,16,30,.98),rgba(19,24,38,.94));border:1px solid rgba(255,255,255,.12);box-shadow:0 20px 60px rgba(0,0,0,.28)}
        .edu-hero h1{margin:0;color:#fff;font-size:clamp(2rem,5vw,3.6rem);letter-spacing:-.045em;font-weight:950}.edu-hero p{max-width:1040px;color:rgba(255,255,255,.74);font-size:1rem;line-height:1.55;margin:.65rem 0 0}.edu-badges{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:1rem}.edu-badge{border:1px solid rgba(0,255,163,.25);background:rgba(0,255,163,.07);color:#b8ffe4;border-radius:999px;padding:.42rem .72rem;font-size:.8rem;font-weight:800}.edu-card{padding:1rem;border-radius:20px;background:linear-gradient(180deg,rgba(255,255,255,.08),rgba(255,255,255,.035));border:1px solid rgba(255,255,255,.11);box-shadow:0 14px 34px rgba(0,0,0,.20);min-height:126px}.edu-card h3{margin:0 0 .35rem;color:#fff4bf;font-size:.96rem}.edu-big{font-size:1.75rem;font-weight:950;color:#fff;letter-spacing:-.03em}.edu-muted{color:rgba(255,255,255,.65);font-size:.88rem;line-height:1.5}.edu-section{margin:.8rem 0 .55rem;font-size:.78rem;text-transform:uppercase;letter-spacing:.16em;font-weight:950;color:#00ffa3}.lesson-card,.play-card{padding:1rem;border-radius:18px;background:rgba(6,10,20,.58);border:1px solid rgba(255,255,255,.10);margin-bottom:.75rem}.lesson-card:hover,.play-card:hover{border-color:rgba(0,255,163,.32);box-shadow:0 0 24px rgba(0,255,163,.10)}.lesson-top{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}.lesson-title{font-size:1rem;font-weight:900;color:#fff}.pill{display:inline-block;border-radius:999px;padding:.22rem .55rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.10);color:rgba(255,255,255,.76);font-size:.76rem;margin:.12rem}.pill-green{background:rgba(0,255,163,.09);border-color:rgba(0,255,163,.25);color:#9cffda}.pill-gold{background:rgba(255,202,40,.10);border-color:rgba(255,202,40,.26);color:#ffe391}.edu-note{padding:1rem;border-radius:18px;background:rgba(255,202,40,.08);border:1px solid rgba(255,202,40,.20);color:rgba(255,255,255,.78)}
        @media(max-width:768px){.edu-hero{padding:1.15rem}.lesson-top{display:block}.edu-card{min-height:auto}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_lesson_card(lesson: dict[str, Any], index: int) -> None:
    checklist = "".join(f'<span class="pill">{item}</span>' for item in lesson["checklist"])
    st.markdown(
        f"""
        <div class="lesson-card">
            <div class="lesson-top">
                <div>
                    <div class="lesson-title">{index}. {lesson['title']}</div>
                    <div class="edu-muted">{lesson['summary']}</div>
                </div>
                <div><span class="pill pill-green">{lesson['level']}</span><span class="pill pill-gold">{lesson['time']}</span></div>
            </div>
            <div style="margin-top:.65rem"><span class="pill pill-green">Focus: {lesson['focus']}</span></div>
            <div style="margin-top:.45rem">{checklist}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_playbook(play: dict[str, str]) -> None:
    st.markdown(
        f"""
        <div class="play-card">
            <div class="lesson-title">{play['name']}</div>
            <div style="margin-top:.4rem"><span class="pill pill-green">Best: {play['best']}</span></div>
            <div class="edu-muted" style="margin-top:.55rem"><b style="color:#fff">Steps:</b> {play['steps']}</div>
            <div class="edu-muted" style="margin-top:.35rem"><b style="color:#fff4bf">Avoid:</b> {play['avoid']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_education_page(role: str = "client") -> None:
    _inject_education_css()
    st.markdown(
        """
        <div class="edu-hero">
          <h1>Trader Education Center</h1>
          <p>Learn the foundations, smart-money concepts, session timing, and execution discipline needed to trade with a repeatable plan. This page replaces the old Accounts page and is built to align cleanly with the Streamlit menu.</p>
          <div class="edu-badges">
            <span class="edu-badge">Beginner Friendly</span><span class="edu-badge">XAUUSD + Indices</span><span class="edu-badge">Risk First</span><span class="edu-badge">ICT/SMC Concepts</span><span class="edu-badge">Session Playbooks</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown('<div class="edu-card"><h3>Learning Path</h3><div class="edu-big">6</div><div class="edu-muted">Core lessons</div></div>', unsafe_allow_html=True)
    c2.markdown('<div class="edu-card"><h3>Playbooks</h3><div class="edu-big">3</div><div class="edu-muted">Repeatable setups</div></div>', unsafe_allow_html=True)
    c3.markdown('<div class="edu-card"><h3>Focus</h3><div class="edu-big">Risk</div><div class="edu-muted">Before entries</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="edu-card"><h3>Updated</h3><div class="edu-big">{datetime.now().strftime("%b %d")}</div><div class="edu-muted">Education page active</div></div>', unsafe_allow_html=True)

    tab_path, tab_playbooks, tab_quiz, tab_notes = st.tabs(["🎓 Learning Path", "📘 Playbooks", "🧠 Quiz", "📝 Session Notes"])

    with tab_path:
        st.markdown('<div class="edu-section">Core modules</div>', unsafe_allow_html=True)
        level = st.selectbox("Filter lessons", ["All", "Foundation", "Smart Money", "Execution"], key="edu_level_filter")
        filtered = [x for x in LESSONS if level == "All" or x["level"] == level]
        for i, lesson in enumerate(filtered, 1):
            _render_lesson_card(lesson, i)

    with tab_playbooks:
        st.markdown('<div class="edu-section">Setup playbooks</div>', unsafe_allow_html=True)
        for play in PLAYBOOKS:
            _render_playbook(play)
        st.markdown('<div class="edu-note"><b>Execution rule:</b> a setup is not valid until structure, session timing, risk, and confirmation all agree.</div>', unsafe_allow_html=True)

    with tab_quiz:
        st.markdown('<div class="edu-section">Knowledge check</div>', unsafe_allow_html=True)
        score = 0
        for i, item in enumerate(QUIZ, 1):
            answer = st.radio(item["question"], item["options"], key=f"edu_quiz_{i}")
            if answer == item["answer"]:
                score += 1
        if st.button("Check Score", use_container_width=True, key="edu_check_score"):
            if score == len(QUIZ):
                st.success(f"Perfect: {score}/{len(QUIZ)}. You are thinking like a disciplined trader.")
            else:
                st.warning(f"Score: {score}/{len(QUIZ)}. Review the missed concepts before live execution.")

    with tab_notes:
        st.markdown('<div class="edu-section">Practice notes</div>', unsafe_allow_html=True)
        st.text_area("What did today’s market teach you?", height=130, placeholder="Example: Asia built equal highs, London swept them, NY respected the FVG after displacement…", key="edu_practice_notes")
        plan = st.text_area("Tomorrow’s trading plan", height=130, placeholder="Bias, sessions to trade, max risk, invalidation rules…", key="edu_plan_notes")
        if st.button("Save Notes In Session", use_container_width=True, key="edu_save_notes"):
            st.session_state["education_saved_notes"] = {"practice": st.session_state.get("edu_practice_notes", ""), "plan": plan, "saved_at": datetime.now().isoformat()}
            st.success("Notes saved for this Streamlit session.")
        if st.session_state.get("education_saved_notes"):
            st.info("Saved in session. For permanent notes, connect this to your existing SQLite trade journal/log store.")


def render_frontend_education_page(role: str = "client") -> None:
    render_education_page(role)


# Backward-compatible aliases so older imports/routes do not break while the app transitions from Accounts to Education.
def render_trading_accounts_page(role: str = "client") -> None:
    render_education_page(role)


def render_accounts(role: str = "client") -> None:
    render_education_page(role)


def render_frontend_accounts_page(role: str = "client") -> None:
    render_education_page(role)


if __name__ == "__main__":
    st.set_page_config(page_title="Education", page_icon="🎓", layout="wide")
    render_education_page("ceo")
