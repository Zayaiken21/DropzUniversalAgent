from pathlib import Path
import sys

import streamlit as st


def _app_root() -> Path:
    """
    Resolve the same project root in localhost, Streamlit Cloud, and PyInstaller EXE.

    Localhost:
        DropzUniversalAgent/frontend/style_loader.py -> parents[1]
    EXE:
        DropzUniversalAgent-Windows/_internal/frontend/style_loader.py -> _MEIPASS/_internal root
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return Path(__file__).resolve().parents[1]


ROOT_DIR = _app_root()


def _read_css(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[CSS LOAD ERROR] {path}: {exc}")
    return ""


def load_theme_css():
    """
    Load all project theme CSS from /styles.

    This intentionally keeps your existing UI structure the same, but fixes the
    packaged EXE path issue so the build reads the exact same CSS files as
    localhost/Streamlit Cloud.
    """
    styles_dir = ROOT_DIR / "styles"

    css_files = [
        "theme.css",
        "dashboard.css",
        "chat_style.css",
        "education.css",
    ]

    css_bundle_parts = []
    for filename in css_files:
        css = _read_css(styles_dir / filename)
        if css:
            css_bundle_parts.append(f"/* {filename} */\n{css}")

    css_bundle = "\n\n".join(css_bundle_parts)

    st.markdown(
        f"""
        <style>
        {css_bundle}
        </style>
        """,
        unsafe_allow_html=True,
    )
