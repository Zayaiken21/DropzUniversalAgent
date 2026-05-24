from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent

def load_theme_css():

    css_bundle = ""

    theme_css = ROOT_DIR / "styles" / "theme.css"

    chat_css = ROOT_DIR / "styles" / "chat_style.css"

    if theme_css.exists():

        try:
            css_bundle += theme_css.read_text(
                encoding="utf-8"
            )

        except Exception as e:
            print(f"[THEME CSS ERROR] {e}")

    if chat_css.exists():

        try:
            css_bundle += "\n\n"
            css_bundle += chat_css.read_text(
                encoding="utf-8"
            )

        except Exception as e:
            print(f"[CHAT CSS ERROR] {e}")

    st.markdown(
        f"""
        <style>

        {css_bundle}

        </style>
        """,
        unsafe_allow_html=True
    )