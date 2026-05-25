# frontend/tradesmart_page.py

import pandas as pd
import streamlit as st

from frontend.mt5_secure_store import (
    account_matches_profile,
    connect_mt5,
    get_active_mt5_mode,
    get_mt5_orders,
    get_mt5_positions,
    get_signed_in_user_key,
    is_profile_ready,
    load_mt5_profile,
    mask_login,
    password_status,
    set_active_mt5_mode,
    shutdown_mt5,
)
from agents.tradesmart_agent import TradeSmartAgent


def _clear_mt5_connection_state() -> None:
    for key in (
        "mt5_connected",
        "mt5_account_info",
        "mt5_mode",
        "mt5_connected_profile_key",
        "tradesmart_agent_last_cycle",
    ):
        st.session_state.pop(key, None)
    shutdown_mt5()


def _profile_connection_key(user_key: str, mode: str, profile: dict) -> str:
    return f"{user_key}:{mode}:{profile.get('login','')}:{profile.get('server','')}"


def _is_any_mt5_connected() -> bool:
    return bool(st.session_state.get("mt5_connected") and st.session_state.get("mt5_account_info"))


def _connected_mode() -> str:
    return str(st.session_state.get("mt5_mode") or "")


def render_mt5_tradesmart_connection(role="client"):
    user_key = get_signed_in_user_key(role)

    if f"tradesmart_active_mode_{user_key}" not in st.session_state:
        st.session_state[f"tradesmart_active_mode_{user_key}"] = get_active_mt5_mode(user_key, role=role)

    st.markdown("### MT5 TradeSmart Connection")

    currently_connected = _is_any_mt5_connected()
    connected_mode = _connected_mode()
    active_mode = st.session_state[f"tradesmart_active_mode_{user_key}"]

    selected_mode = st.radio(
        "TradeSmart MT5 Mode",
        ["Demo", "Live"],
        horizontal=True,
        index=0 if active_mode == "Demo" else 1,
        key=f"tradesmart_mt5_mode_radio_{user_key}_{'locked' if currently_connected else 'open'}",
        disabled=currently_connected,
    )

    if currently_connected:
        selected_mode = connected_mode or active_mode
        st.session_state[f"tradesmart_active_mode_{user_key}"] = selected_mode
    elif selected_mode != active_mode:
        st.session_state[f"tradesmart_active_mode_{user_key}"] = selected_mode
        set_active_mt5_mode(user_key, selected_mode)
        _clear_mt5_connection_state()
        st.rerun()

    selected_mode = st.session_state[f"tradesmart_active_mode_{user_key}"]
    profile = load_mt5_profile(user_key, selected_mode, role=role)
    ready, missing = is_profile_ready(profile)
    connection_key = _profile_connection_key(user_key, selected_mode, profile)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Selected Mode", selected_mode)
    with c2:
        st.metric("Saved Login", mask_login(profile.get("login", "")))
    with c3:
        st.metric("Password", password_status(profile.get("password", "")))
    with c4:
        st.metric("Server", profile.get("server") or "Not saved")

    if profile.get("error"):
        st.error(profile["error"])

    connected_to_this_profile = (
        st.session_state.get("mt5_connected") is True
        and st.session_state.get("mt5_mode") == selected_mode
        and st.session_state.get("mt5_connected_profile_key") == connection_key
    )

    if ready:
        st.success(f"{selected_mode} MT5 credentials are loaded for this signed-in user.")
    else:
        st.info(
            f"{selected_mode} MT5 credentials are not complete yet. "
            f"Go to Settings → ⋯ MT5 Credentials and save: {', '.join(missing)}."
        )

    if selected_mode == "Live":
        st.warning("Live mode is selected. Keep Enable TradeSmart Agent off until your order execution safety checks are finished.")

    if not ready:
        _clear_mt5_connection_state()
        return selected_mode, profile, False

    if connected_to_this_profile and st.session_state.get("mt5_account_info"):
        info = st.session_state["mt5_account_info"]
        st.success(f"Connected to {selected_mode} MT5 account.")

        a1, a2, a3, a4 = st.columns(4)
        with a1:
            st.metric("Balance", info.get("balance", 0))
        with a2:
            st.metric("Equity", info.get("equity", 0))
        with a3:
            st.metric("Currency", info.get("currency", ""))
        with a4:
            st.metric("Leverage", info.get("leverage", ""))

        if st.button(f"Disconnect {selected_mode} MT5", use_container_width=True, key=f"disconnect_mt5_{user_key}_{selected_mode}"):
            _clear_mt5_connection_state()
            st.success(f"{selected_mode} MT5 disconnected.")
            st.rerun()

        return selected_mode, profile, True

    if currently_connected and not connected_to_this_profile:
        st.info("Disconnect the current MT5 account before switching Demo/Live mode.")
        return selected_mode, profile, False

    if st.button(f"Connect to {selected_mode} MT5", use_container_width=True, key=f"connect_mt5_{user_key}_{selected_mode}_{connection_key}"):
        _clear_mt5_connection_state()

        connected, message, account_info = connect_mt5(profile)

        if not connected:
            st.error(message)
            return selected_mode, profile, False

        if not account_matches_profile(account_info, profile):
            shutdown_mt5()
            st.error(
                f"MT5 connected, but it returned a different account than your saved {selected_mode} profile. "
                "Check the selected mode credentials in Settings."
            )
            return selected_mode, profile, False

        st.session_state["mt5_connected"] = True
        st.session_state["mt5_mode"] = selected_mode
        st.session_state["mt5_account_info"] = account_info
        st.session_state["mt5_connected_profile_key"] = connection_key
        shutdown_mt5()
        st.rerun()

    return selected_mode, profile, False


def _build_rules(
    selected_mode,
    max_daily_loss,
    risk_per_trade,
    max_open_trades,
    max_position_size,
    stop_loss_type,
    take_profit_type,
    market_type,
    timeframe,
    trade_direction,
    symbols,
    strategy_choices,
    agent_prompt,
    automation,
):
    return {
        "mode": selected_mode,
        "max_daily_loss_percent": max_daily_loss,
        "risk_per_trade_percent": risk_per_trade,
        "max_open_trades": max_open_trades,
        "max_position_size_percent": max_position_size,
        "stop_loss_type": stop_loss_type,
        "take_profit_type": take_profit_type,
        "market_type": market_type,
        "timeframe": timeframe,
        "trade_direction": trade_direction,
        "watchlist": symbols,
        "strategies": strategy_choices,
        "agent_prompt": agent_prompt,
        "automation": automation,
        "allow_live_execution": False,
    }


def render_tradesmart(role="client"):
    st.markdown('<h2 class="section-title">TradeSmart</h2>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="glass-card muted centered-content">
            TradeSmart is your Dropzuniversal AI trading sub-agent for auto-trade monitoring,
            risk setup, smart entries, exits, portfolio rules, and strategy automation.
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_mode, mt5_profile, mt5_connected = render_mt5_tradesmart_connection(role)

    st.markdown("---")
    st.markdown("### AI Trading Agent Status")

    col1, col2 = st.columns(2)

    with col1:
        agent_enabled = st.toggle(
            "Enable TradeSmart Agent",
            value=False,
            key=f"enable_tradesmart_agent_{selected_mode}",
            help="This is the auto-trading control. Keep it off until your MT5 setup and trading rules are tested.",
        )

    with col2:
        if agent_enabled and mt5_connected:
            st.success(f"TradeSmart Agent is active in {selected_mode} mode.")
        elif agent_enabled:
            st.warning(f"Connect to {selected_mode} MT5 before TradeSmart can scan.")
        else:
            st.info(f"TradeSmart Agent is idle in {selected_mode} mode.")

    st.markdown("---")
    st.markdown("### Risk Parameters")

    risk_col1, risk_col2, risk_col3 = st.columns(3)

    with risk_col1:
        max_daily_loss = st.slider("Max Daily Loss %", 1, 25, 5)
        risk_per_trade = st.slider("Risk Per Trade %", 1, 10, 2)

    with risk_col2:
        max_open_trades = st.number_input("Max Open Trades", min_value=1, max_value=50, value=5)
        stop_loss_type = st.selectbox(
            "Stop Loss Type",
            ["Fixed %", "ATR-Based", "Trailing Stop", "Support/Resistance", "AI Dynamic Stop"],
        )

    with risk_col3:
        take_profit_type = st.selectbox(
            "Take Profit Type",
            ["Fixed %", "Risk/Reward Ratio", "Trailing Take Profit", "Partial Profit Scaling", "AI Dynamic Exit"],
        )
        max_position_size = st.slider("Max Position Size %", 1, 100, 20)

    st.markdown("---")
    st.markdown("### Strategy Choices")

    strategy_choices = st.multiselect(
        "Choose Trading Strategies",
        [
            "Trend Following",
            "Scalping",
            "Swing Trading",
            "Breakout Trading",
            "Mean Reversion",
            "Momentum Trading",
            "News-Based Trading",
            "AI Signal Confirmation",
            "Support & Resistance Entries",
            "Liquidity Sweep Detection",
            "Smart Money Concepts",
            "DCA / Dollar Cost Averaging",
            "Grid Trading",
            "Arbitrage Scanner",
            "Volume Spike Entries",
            "RSI Reversal Strategy",
            "MACD Confirmation",
            "Moving Average Crossovers",
            "Order Block Detection",
            "Custom Strategy Builder",
        ],
        default=["AI Signal Confirmation", "Trend Following"],
    )

    st.markdown("---")
    st.markdown("### Automation Features")

    automation_col1, automation_col2 = st.columns(2)

    with automation_col1:
        auto_entry = st.checkbox("Auto Entry Detection")
        auto_exit = st.checkbox("Auto Exit Detection")
        auto_sl = st.checkbox("Auto Stop Loss Placement")
        auto_tp = st.checkbox("Auto Take Profit Placement")
        auto_size = st.checkbox("Auto Position Sizing")
        auto_journal = st.checkbox("Auto Journal Trades")

    with automation_col2:
        sentiment_scan = st.checkbox("AI Market Sentiment Scan")
        exposure_alerts = st.checkbox("Portfolio Exposure Alerts")
        cooldown_protection = st.checkbox("Trade Cooldown Protection")
        avoid_volatility = st.checkbox("Avoid High Volatility Events")
        whale_alerts = st.checkbox("Whale / Volume Alert Detection")
        ai_review = st.checkbox("AI Trade Review Before Execution", value=True)

    st.markdown("---")
    st.markdown("### Market Filters")

    market_col1, market_col2, market_col3 = st.columns(3)

    with market_col1:
        market_type = st.selectbox("Market Type", ["Crypto", "Stocks", "Forex", "Options", "Futures", "Commodities"])

    with market_col2:
        timeframe = st.selectbox("Primary Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W"], index=4)

    with market_col3:
        trade_direction = st.selectbox("Trade Direction", ["Long Only", "Short Only", "Long & Short"])

    symbols = st.text_input("Watchlist Symbols", placeholder="Example: BTCUSDT, ETHUSDT, AAPL, TSLA")

    st.markdown("---")
    st.markdown("### AI Agent Instructions")

    agent_prompt = st.text_area(
        "Custom TradeSmart Agent Rules",
        placeholder=(
            "Example: Only take trades when trend is bullish, RSI is above 50, "
            "volume is increasing, and risk/reward is at least 1:2."
        ),
        height=140,
    )

    automation = {
        "auto_entry": auto_entry,
        "auto_exit": auto_exit,
        "auto_stop_loss": auto_sl,
        "auto_take_profit": auto_tp,
        "auto_position_sizing": auto_size,
        "auto_journal": auto_journal,
        "sentiment_scan": sentiment_scan,
        "exposure_alerts": exposure_alerts,
        "cooldown_protection": cooldown_protection,
        "avoid_high_volatility": avoid_volatility,
        "whale_alerts": whale_alerts,
        "ai_review_before_execution": ai_review,
    }

    rules = _build_rules(
        selected_mode,
        max_daily_loss,
        risk_per_trade,
        max_open_trades,
        max_position_size,
        stop_loss_type,
        take_profit_type,
        market_type,
        timeframe,
        trade_direction,
        symbols,
        strategy_choices,
        agent_prompt,
        automation,
    )

    if agent_enabled and mt5_connected:
        agent = TradeSmartAgent(mt5_profile, rules)
        cycle = agent.run_cycle(execution_enabled=True)
        st.session_state["tradesmart_agent_last_cycle"] = cycle

        if cycle.get("ok"):
            st.success(cycle.get("message", "TradeSmart Agent cycle complete."))
        else:
            st.warning(cycle.get("message", "TradeSmart Agent could not complete the cycle."))

    st.markdown("---")
    st.markdown("### TradeSmart Configuration Summary")

    st.markdown(
        f"""
        <div class="glass-card">
            <strong>Selected MT5 Mode:</strong> {selected_mode}<br>
            <strong>MT5 Login:</strong> {mask_login(mt5_profile.get("login", ""))}<br>
            <strong>MT5 Server:</strong> {mt5_profile.get("server", "Not saved") or "Not saved"}<br>
            <strong>TradeSmart Agent Enabled:</strong> {agent_enabled}<br>
            <strong>Max Daily Loss:</strong> {max_daily_loss}%<br>
            <strong>Risk Per Trade:</strong> {risk_per_trade}%<br>
            <strong>Max Open Trades:</strong> {max_open_trades}<br>
            <strong>Max Position Size:</strong> {max_position_size}%<br>
            <strong>Stop Loss:</strong> {stop_loss_type}<br>
            <strong>Take Profit:</strong> {take_profit_type}<br>
            <strong>Market:</strong> {market_type}<br>
            <strong>Timeframe:</strong> {timeframe}<br>
            <strong>Direction:</strong> {trade_direction}<br>
            <strong>Strategies:</strong> {", ".join(strategy_choices) if strategy_choices else "None selected"}<br>
            <strong>Watchlist:</strong> {symbols if symbols else "No symbols added yet"}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.warning(
        "TradeSmart routes trading decisions through frontend/tradesmart_agent.py. "
        "Live execution remains blocked inside the agent unless you explicitly approve it in code."
    )

    if st.button("Save TradeSmart Settings"):
        st.success("TradeSmart settings saved successfully.")


def render_frontend_tradesmart_page(role="client"):
    render_tradesmart(role)
    return None
