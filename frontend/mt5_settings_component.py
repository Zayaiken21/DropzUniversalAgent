# frontend/mt5_settings_component.py

import streamlit as st

from frontend.mt5_secure_store import (
    clear_mt5_profile,
    connect_mt5,
    get_active_mt5_mode,
    get_signed_in_user_key,
    is_profile_ready,
    load_mt5_profile,
    mask_login,
    password_status,
    profile_fingerprint,
    save_mt5_profile_for_current_user,
    set_active_mt5_mode,
    shutdown_mt5,
)


def _clear_connection_state() -> None:
    for key in (
        "mt5_connected",
        "mt5_account_info",
        "mt5_mode",
        "mt5_connected_profile_key",
        "tradesmart_agent_last_cycle",
    ):
        st.session_state.pop(key, None)
    shutdown_mt5()


def _set_mode(user_key: str, selected_mode: str) -> None:
    selected_mode = selected_mode.title()
    st.session_state[f"mt5_active_mode_{user_key}"] = selected_mode
    st.session_state[f"tradesmart_active_mode_{user_key}"] = selected_mode
    set_active_mt5_mode(user_key, selected_mode)
    _clear_connection_state()


def render_mt5_credentials_settings(role: str = "client") -> None:
    user_key = get_signed_in_user_key(role)

    if f"mt5_active_mode_{user_key}" not in st.session_state:
        st.session_state[f"mt5_active_mode_{user_key}"] = get_active_mt5_mode(user_key, role=role)

    st.markdown("---")

    with st.expander("⋯ MT5 Credentials", expanded=False):
        st.caption(
            "Demo and Live credentials are saved separately. "
            "Choose a mode to edit only that mode's MT5 login, password, and server."
        )

        active_mode = st.session_state[f"mt5_active_mode_{user_key}"]

        selected_mode = st.radio(
            "MT5 Account Mode",
            ["Demo", "Live"],
            horizontal=True,
            index=0 if active_mode == "Demo" else 1,
            key=f"mt5_settings_mode_radio_{user_key}",
        )

        if selected_mode != active_mode:
            _set_mode(user_key, selected_mode)
            st.rerun()

        selected_mode = st.session_state[f"mt5_active_mode_{user_key}"]
        saved = load_mt5_profile(user_key, selected_mode, role=role)
        ready, missing = is_profile_ready(saved)
        fp = profile_fingerprint(saved)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Selected Mode", selected_mode)
        with c2:
            st.metric("Saved Login", mask_login(saved.get("login", "")))
        with c3:
            st.metric("Password", password_status(saved.get("password", "")))
        with c4:
            st.metric("Server", saved.get("server") or "Not saved")

        if ready:
            st.success(f"{selected_mode} MT5 credentials are saved for this signed-in user.")
        elif saved.get("login") or saved.get("password") or saved.get("server"):
            st.warning(f"{selected_mode} profile is partially saved. Missing: {', '.join(missing)}.")
        else:
            st.info(f"No {selected_mode} MT5 credentials saved yet.")

        with st.form(key=f"mt5_form_{user_key}_{selected_mode}_{fp}", clear_on_submit=False):
            mt5_login = st.text_input(
                "MT5 Login",
                value=saved.get("login", ""),
                placeholder="Enter MT5 login number",
                key=f"mt5_login_input_{user_key}_{selected_mode}_{fp}",
            )

            mt5_password = st.text_input(
                "MT5 Password",
                value=saved.get("password", ""),
                type="password",
                placeholder="Enter MT5 password",
                key=f"mt5_password_input_{user_key}_{selected_mode}_{fp}",
            )

            mt5_server = st.text_input(
                "MT5 Server",
                value=saved.get("server", ""),
                placeholder="Exact MT5 server name from your broker login window",
                key=f"mt5_server_input_{user_key}_{selected_mode}_{fp}",
            )

            advanced_open = st.checkbox(
                "Show advanced MT5 terminal options",
                value=bool(saved.get("terminal_path")),
                key=f"mt5_advanced_{user_key}_{selected_mode}_{fp}",
            )

            terminal_path = saved.get("terminal_path", "")
            timeout = int(saved.get("timeout", 10000) or 10000)
            portable = bool(saved.get("portable", False))

            if advanced_open:
                terminal_path = st.text_input(
                    "MT5 Terminal Path",
                    value=saved.get("terminal_path", ""),
                    placeholder=r"C:\Program Files\MetaTrader 5\terminal64.exe",
                    key=f"mt5_terminal_path_{user_key}_{selected_mode}_{fp}",
                )

                timeout = st.number_input(
                    "Connection Timeout",
                    min_value=1000,
                    max_value=60000,
                    value=int(saved.get("timeout", 10000) or 10000),
                    step=1000,
                    key=f"mt5_timeout_{user_key}_{selected_mode}_{fp}",
                )

                portable = st.checkbox(
                    "Portable Terminal Mode",
                    value=bool(saved.get("portable", False)),
                    key=f"mt5_portable_{user_key}_{selected_mode}_{fp}",
                )

            b1, b2, b3 = st.columns([2, 2, 1])
            with b1:
                save_clicked = st.form_submit_button(
                    f"Save {selected_mode} MT5 Credentials",
                    use_container_width=True,
                )
            with b2:
                test_clicked = st.form_submit_button(
                    f"Test {selected_mode} Connection",
                    use_container_width=True,
                )
            with b3:
                clear_clicked = st.form_submit_button(
                    "Clear",
                    use_container_width=True,
                )

        current_profile = {
            "mode": selected_mode,
            "login": mt5_login,
            "password": mt5_password,
            "server": mt5_server,
            "terminal_path": terminal_path,
            "timeout": timeout,
            "portable": portable,
        }
        current_ready, current_missing = is_profile_ready(current_profile)

        if clear_clicked:
            clear_mt5_profile(user_key, selected_mode, role=role)

            # Remove stale widget values for this selected mode so the cleared
            # profile does not visually repopulate from Streamlit session state.
            for state_key in list(st.session_state.keys()):
                key_text = str(state_key)
                if (
                    key_text.startswith(("mt5_login_input_", "mt5_password_input_", "mt5_server_input_", "mt5_terminal_path_", "mt5_timeout_", "mt5_portable_", "mt5_advanced_"))
                    and f"_{user_key}_{selected_mode}_" in key_text
                ):
                    st.session_state.pop(state_key, None)

            _set_mode(user_key, selected_mode)
            st.success(f"{selected_mode} MT5 credentials cleared.")
            st.rerun()

        if save_clicked or test_clicked:
            save_mt5_profile_for_current_user(selected_mode, current_profile, role=role)
            _set_mode(user_key, selected_mode)

            if current_ready:
                st.success(f"{selected_mode} MT5 credentials saved.")
            else:
                st.warning(f"{selected_mode} MT5 profile saved but still missing: {', '.join(current_missing)}.")

            if test_clicked and current_ready:
                connected, message, account_info = connect_mt5(current_profile)
                if connected:
                    st.success(f"{selected_mode} MT5 connection verified.")
                    st.json({
                        "login": account_info.get("login"),
                        "server": account_info.get("server"),
                        "balance": account_info.get("balance"),
                        "equity": account_info.get("equity"),
                        "currency": account_info.get("currency"),
                        "leverage": account_info.get("leverage"),
                    })
                else:
                    st.error(message)
                shutdown_mt5()
            elif test_clicked:
                st.error(f"Cannot test yet. Missing: {', '.join(current_missing)}.")

            st.rerun()
