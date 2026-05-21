from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
THEME_PATH = ROOT_DIR / "frontend" / "theme.css"

def load_theme_css():
    if THEME_PATH.exists():
        with open(THEME_PATH, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)