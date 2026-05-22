from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent

STYLES_DIR = ROOT_DIR / "styles"

def load_theme_css():

    css_bundle = ""

    # Load ALL css files in styles folder
    if STYLES_DIR.exists():

        for file in sorted(STYLES_DIR.glob("*.css")):

            try:
                css_bundle += file.read_text(encoding="utf-8") + "\n"

            except Exception as e:
                print(f"[CSS LOAD ERROR] {file} -> {e}")

    # Fallback (your old theme.css support still works if you move it later)
    legacy_theme = ROOT_DIR / "frontend" / "theme.css"

    if legacy_theme.exists():

        try:
            css_bundle += legacy_theme.read_text(encoding="utf-8")

        except Exception as e:
            print(f"[LEGACY CSS ERROR] {e}")

    if css_bundle:

        st.markdown(
            f"""
            <style>
            {css_bundle}
            </style>
            """,
            unsafe_allow_html=True
        )