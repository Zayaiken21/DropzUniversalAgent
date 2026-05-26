import streamlit as st

from frontend.tradesmart_bridge_store import (
    get_current_user_key,
    load_bridge_settings,
    save_bridge_settings,
    mask_secret,
)
from frontend.tradesmart_bridge_client import get_bridge_status


def render_tradesmart_bridge_settings(scope: str = "settings"):
    """
    Render this ONLY inside a settings page render function.
    Do not call it at the top level of settings_ceo_page.py or settings_client_page.py.
    """
    user_key = get_current_user_key(scope)
    saved = load_bridge_settings(user_key)
    prefix = f"tradesmart_bridge_{scope}_{user_key}"

    with st.expander("⋯ TradeSmart Windows Bridge", expanded=False):
        st.markdown(
            """
            <div class="glass-card">
                Connect this account to the Windows PC where MetaTrader 5 is installed and running.
                TradeSmart is locked to <strong>XAUUSD</strong>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        bridge_url = st.text_input(
            "Windows Bridge URL",
            value=saved.get("bridge_url", ""),
            placeholder="Example: https://your-ngrok-url.ngrok-free.app",
            key=f"{prefix}_url",
        )

        bridge_token = st.text_input(
            "Windows Bridge API Token",
            value=saved.get("bridge_token", ""),
            type="password",
            placeholder="Must match local_windows_bridge/.env BRIDGE_TOKEN",
            key=f"{prefix}_token",
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Save Bridge Settings", use_container_width=True, key=f"{prefix}_save"):
                save_bridge_settings(user_key, bridge_url, bridge_token)
                st.success("TradeSmart Windows Bridge settings saved.")
                st.rerun()

        with col2:
            if st.button("Test Bridge", use_container_width=True, key=f"{prefix}_test"):
                temp_settings = {"bridge_url": bridge_url, "bridge_token": bridge_token}
                ok, result = get_bridge_status(temp_settings)
                if ok:
                    st.success("Bridge is reachable.")
                else:
                    st.error(result.get("message", "Bridge test failed."))

        st.caption(f"Saved URL: {saved.get('bridge_url') or 'Not saved'}")
        st.caption(f"Saved Token: {mask_secret(saved.get('bridge_token', ''))}")
