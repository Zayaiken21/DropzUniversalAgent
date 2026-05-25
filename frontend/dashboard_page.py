# frontend/dashboard_page.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def inject_dashboard_styles():
    st.markdown(
        """
        <style>
            .dashboard-hero {
                padding: 34px;
                border-radius: 28px;
                background:
                    radial-gradient(circle at top left, rgba(0,255,163,.18), transparent 35%),
                    radial-gradient(circle at bottom right, rgba(93,95,239,.22), transparent 35%),
                    linear-gradient(135deg, rgba(255,255,255,.09), rgba(255,255,255,.035));
                border: 1px solid rgba(255,255,255,.12);
                box-shadow: 0 24px 80px rgba(0,0,0,.35);
                backdrop-filter: blur(18px);
                margin-bottom: 28px;
            }

            .dashboard-eyebrow {
                font-size: 13px;
                letter-spacing: 2px;
                text-transform: uppercase;
                color: #00ffa3;
                font-weight: 700;
                margin-bottom: 10px;
            }

            .dashboard-title {
                font-size: 42px;
                line-height: 1.05;
                font-weight: 900;
                color: #ffffff;
                margin-bottom: 10px;
            }

            .dashboard-sub {
                color: rgba(255,255,255,.68);
                font-size: 16px;
                max-width: 760px;
            }

            .kpi-card {
                padding: 22px;
                border-radius: 22px;
                background: linear-gradient(145deg, rgba(255,255,255,.095), rgba(255,255,255,.035));
                border: 1px solid rgba(255,255,255,.11);
                box-shadow: 0 18px 50px rgba(0,0,0,.28);
                min-height: 132px;
            }

            .kpi-title {
                color: rgba(255,255,255,.55);
                font-size: 13px;
                text-transform: uppercase;
                letter-spacing: 1.3px;
                font-weight: 700;
            }

            .kpi-value {
                color: #ffffff;
                font-size: 31px;
                font-weight: 900;
                margin-top: 12px;
            }

            .kpi-change {
                margin-top: 10px;
                color: #00ffa3;
                font-size: 13px;
                font-weight: 700;
            }

            .pro-card {
                padding: 24px;
                border-radius: 24px;
                background: linear-gradient(145deg, rgba(255,255,255,.085), rgba(255,255,255,.03));
                border: 1px solid rgba(255,255,255,.105);
                box-shadow: 0 20px 60px rgba(0,0,0,.25);
                margin-bottom: 22px;
            }

            .card-heading {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 14px;
            }

            .card-heading h3 {
                margin: 0;
                color: #fff;
                font-size: 20px;
                font-weight: 850;
            }

            .pill {
                padding: 7px 11px;
                border-radius: 999px;
                background: rgba(0,255,163,.12);
                border: 1px solid rgba(0,255,163,.25);
                color: #00ffa3;
                font-size: 12px;
                font-weight: 800;
            }

            .activity-item {
                padding: 14px 0;
                border-bottom: 1px solid rgba(255,255,255,.08);
                color: rgba(255,255,255,.78);
                font-size: 14px;
            }

            .activity-item:last-child {
                border-bottom: none;
            }

            .mini-label {
                color: rgba(255,255,255,.55);
                font-size: 13px;
                margin-bottom: 6px;
            }

            .mini-value {
                color: white;
                font-size: 20px;
                font-weight: 850;
                margin-bottom: 14px;
            }

            .dashboard-section-space {
                height: 16px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def circular_chart(title, value):
    if value >= 70:
        color = "#00FFA3"
    elif value >= 50:
        color = "#FFD166"
    else:
        color = "#FF4D6D"

    fig = go.Figure(
        go.Pie(
            values=[value, 100 - value],
            hole=0.82,
            marker_colors=[color, "rgba(255,255,255,.07)"],
            textinfo="none",
            sort=False,
        )
    )

    fig.update_layout(
        height=245,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(t=15, b=15, l=15, r=15),
        annotations=[
            dict(
                text=f"<b>{value}%</b><br><span style='font-size:13px'>{title}</span>",
                x=0.5,
                y=0.5,
                font_size=25,
                showarrow=False,
                font_color="white",
            )
        ],
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )


def render_frontend_dashboard_page(role):
    inject_dashboard_styles()

    st.markdown(
        """
        <div class="dashboard-hero">
            <div class="dashboard-eyebrow">Dropzuniversal Command Center</div>
            <div class="dashboard-title">⚡ Trading Intelligence</div>
            <div class="dashboard-sub">
                Performance analytics, execution discipline, risk visibility,
                and AI-assisted trading insights in one premium dashboard.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(4)

    kpis = [
        ("Win Rate", "72%", "▲ +4.8% this month"),
        ("Total PnL", "$12,450", "▲ +$2,130 net gain"),
        ("Trades", "255", "● 18 active setups"),
        ("Current Streak", "5 Wins", "▲ Momentum strong"),
    ]

    for col, item in zip(cols, kpis):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">{item[0]}</div>
                    <div class="kpi-value">{item[1]}</div>
                    <div class="kpi-change">{item[2]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div class="dashboard-section-space"></div>', unsafe_allow_html=True)

    left, right = st.columns([2.2, 1])

    with left:
        st.markdown(
            """
            <div class="pro-card">
                <div class="card-heading">
                    <h3>Winrate Performance</h3>
                    <div class="pill">Live Analytics</div>
                </div>
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
            """
            <div class="pro-card">
                <div class="card-heading">
                    <h3>Recent Trades</h3>
                    <div class="pill">Execution Log</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        df = pd.DataFrame(
            [
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
            ]
        )

        st.dataframe(df, width="stretch", height=420)

    with right:
        st.markdown(
            """
            <div class="pro-card">
                <div class="card-heading">
                    <h3>Psychology Metrics</h3>
                    <div class="pill">Mindset</div>
                </div>

                <div class="mini-label">Disciplined Trades</div>
                <div class="mini-value">81%</div>

                <div class="mini-label">Confidence</div>
                <div class="mini-value">77%</div>

                <div class="mini-label">Fearful Trades</div>
                <div class="mini-value">14%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.success("Win rate is significantly higher during disciplined sessions.")

        st.markdown(
            """
            <div class="pro-card">
                <div class="card-heading">
                    <h3>Goals Progress</h3>
                    <div class="pill">Targets</div>
                </div>
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
            """
            <div class="pro-card">
                <div class="card-heading">
                    <h3>Activity Feed</h3>
                    <div class="pill">Recent</div>
                </div>

                <div class="activity-item">✓ 5-win streak achieved</div>
                <div class="activity-item">✓ Best trading day this month</div>
                <div class="activity-item">✓ New strategy uploaded</div>
            </div>
            """,
            unsafe_allow_html=True,
        )