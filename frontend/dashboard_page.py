# frontend/dashboard_page.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def circular_chart(title, value):

    if value >= 70:
        color = "#00FFA3"

    elif value >= 50:
        color = "#FFD166"

    else:
        color = "#FF4D6D"

    fig = go.Figure(go.Pie(
        values=[value, 100 - value],
        hole=0.82,
        marker_colors=[color, "#1c1f26"],
        textinfo='none'
    ))

    fig.update_layout(
        height=260,
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(t=20, b=20, l=20, r=20),
        annotations=[
            dict(
                text=f"<b>{value}%</b><br>{title}",
                x=0.5,
                y=0.5,
                font_size=24,
                showarrow=False,
                font_color="white"
            )
        ]
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displayModeBar": False,
            "responsive": True,
        }
    )


def render_frontend_dashboard_page(role):

    st.markdown(
        """
        <div class="dashboard-shell">

            <div class="glass-card centered-content">
                <div class="dashboard-title">
                    ⚡ Trading Intelligence
                </div>

                <div class="dashboard-sub">
                    Performance analytics & execution intelligence
                </div>
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="dashboard-section-space"></div>',
        unsafe_allow_html=True
    )

    cols = st.columns(4)

    kpis = [
        ("Win Rate", "72%"),
        ("Total PnL", "$12,450"),
        ("Trades", "255"),
        ("Current Streak", "5 Wins"),
    ]

    for col, item in zip(cols, kpis):

        with col:

            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">{item[0]}</div>
                    <div class="kpi-value">{item[1]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="dashboard-section-space"></div>',
        unsafe_allow_html=True
    )

    left, right = st.columns([2.2, 1])

    with left:

        st.markdown(
            """
            <div class="glass-card">
                <h3>Winrate Performance</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        top = st.columns(3)

        with top[0]:
            circular_chart("Overall", 72)

        with top[1]:
            circular_chart("Monthly", 69)

        with top[2]:
            circular_chart("Weekly", 74)

        st.markdown(
            '<div class="dashboard-section-space"></div>',
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <div class="glass-card">
                <h3>Recent Trades</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        df = pd.DataFrame([
            {
                "Asset": "BTC/USD",
                "Direction": "Long",
                "PnL": "+$800",
                "RR": "2.5R",
                "Result": "Win",
                "Date": "2026-05-21",
            },
            {
                "Asset": "EUR/USD",
                "Direction": "Short",
                "PnL": "+$520",
                "RR": "1.8R",
                "Result": "Win",
                "Date": "2026-05-21",
            },
        ])

        st.dataframe(
            df,
            width="stretch",
            height=420,
        )

    with right:

        st.markdown(
            """
            <div class="glass-card">
                <h3>Psychology Metrics</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.metric("Disciplined Trades", "81%")
        st.metric("Confidence", "77%")
        st.metric("Fearful Trades", "14%")

        st.success(
            "Win rate is significantly higher during disciplined sessions."
        )

        st.markdown(
            '<div class="dashboard-section-space"></div>',
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <div class="glass-card">
                <h3>Goals Progress</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.progress(0.74)
        st.caption("Monthly Profit Goal — 74%")

        st.progress(0.81)
        st.caption("Consistency Goal — 81%")

        st.progress(0.69)
        st.caption("Win Rate Goal — 69%")

        st.markdown(
            '<div class="dashboard-section-space"></div>',
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <div class="glass-card">
                <h3>Activity Feed</h3>

                <div class="activity-item">
                    ✓ 5-win streak achieved
                </div>

                <div class="activity-item">
                    ✓ Best trading day this month
                </div>

                <div class="activity-item">
                    ✓ New strategy uploaded
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )