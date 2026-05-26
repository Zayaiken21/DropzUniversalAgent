from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_performance_charts(data):
    metrics = data.get("metrics", {})
    labels = ["Daily", "Weekly", "Monthly"]
    values = [
        float(metrics.get("daily_pnl", 0) or 0),
        float(metrics.get("weekly_pnl", 0) or 0),
        float(metrics.get("monthly_pnl", 0) or 0),
    ]

    colors = ["#00ffa3" if value >= 0 else "#ff4d6d" for value in values]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            text=[f"{value:,.2f}" for value in values],
            textposition="outside",
            marker=dict(color=colors, line=dict(color="rgba(255,255,255,.18)", width=1)),
            hovertemplate="%{x} P/L: %{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.025)",
        font=dict(color="white"),
        margin=dict(l=20, r=20, t=36, b=20),
        yaxis=dict(
            title="",
            zeroline=True,
            zerolinecolor="rgba(255,255,255,.22)",
            gridcolor="rgba(255,255,255,.08)",
        ),
        xaxis=dict(title="", gridcolor="rgba(255,255,255,.04)"),
        bargap=0.38,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
