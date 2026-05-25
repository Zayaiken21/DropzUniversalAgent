import streamlit as st


def render_tradesmart():
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

    st.markdown("### AI Trading Agent Status")

    col1, col2, col3 = st.columns(3)

    with col1:
        agent_enabled = st.toggle("Enable TradeSmart Agent", value=False)

    with col2:
        auto_trade = st.toggle("Auto Trading Mode", value=False)

    with col3:
        paper_mode = st.toggle("Paper Trading Mode", value=True)

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
            [
                "Fixed %",
                "ATR-Based",
                "Trailing Stop",
                "Support/Resistance",
                "AI Dynamic Stop",
            ],
        )

    with risk_col3:
        take_profit_type = st.selectbox(
            "Take Profit Type",
            [
                "Fixed %",
                "Risk/Reward Ratio",
                "Trailing Take Profit",
                "Partial Profit Scaling",
                "AI Dynamic Exit",
            ],
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
        st.checkbox("Auto Entry Detection")
        st.checkbox("Auto Exit Detection")
        st.checkbox("Auto Stop Loss Placement")
        st.checkbox("Auto Take Profit Placement")
        st.checkbox("Auto Position Sizing")
        st.checkbox("Auto Journal Trades")

    with automation_col2:
        st.checkbox("AI Market Sentiment Scan")
        st.checkbox("Portfolio Exposure Alerts")
        st.checkbox("Trade Cooldown Protection")
        st.checkbox("Avoid High Volatility Events")
        st.checkbox("Whale / Volume Alert Detection")
        st.checkbox("AI Trade Review Before Execution")

    st.markdown("---")

    st.markdown("### Market Filters")

    market_col1, market_col2, market_col3 = st.columns(3)

    with market_col1:
        market_type = st.selectbox(
            "Market Type",
            ["Crypto", "Stocks", "Forex", "Options", "Futures", "Commodities"],
        )

    with market_col2:
        timeframe = st.selectbox(
            "Primary Timeframe",
            ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W"],
            index=4,
        )

    with market_col3:
        trade_direction = st.selectbox(
            "Trade Direction",
            ["Long Only", "Short Only", "Long & Short"],
        )

    symbols = st.text_input(
        "Watchlist Symbols",
        placeholder="Example: BTCUSDT, ETHUSDT, AAPL, TSLA",
    )

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

    st.markdown("---")

    st.markdown("### TradeSmart Configuration Summary")

    st.markdown(
        f"""
        <div class="glass-card">
            <strong>Agent Enabled:</strong> {agent_enabled}<br>
            <strong>Auto Trading:</strong> {auto_trade}<br>
            <strong>Paper Trading:</strong> {paper_mode}<br>
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
        "TradeSmart configuration is for automation setup only. "
        "Connect broker/exchange execution logic separately and test in paper mode first."
    )

    if st.button("Save TradeSmart Settings"):
        st.success("TradeSmart settings saved successfully.")


def render_frontend_tradesmart_page():
    render_tradesmart()
    return None