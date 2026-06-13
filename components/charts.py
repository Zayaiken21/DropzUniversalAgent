from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def _pnl_bar_chart(metrics):
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
            textfont=dict(color="rgba(255,255,255,.85)", size=13),
            marker=dict(
                color=colors,
                line=dict(color="rgba(255,255,255,.18)", width=1),
            ),
            hovertemplate="<b>%{x} P/L</b><br>%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text="P/L Overview", font=dict(size=15, color="rgba(255,255,255,.85)"), x=0.02),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.025)",
        font=dict(color="white", family="Inter, sans-serif"),
        margin=dict(l=20, r=20, t=46, b=20),
        yaxis=dict(
            title="",
            zeroline=True,
            zerolinecolor="rgba(255,255,255,.22)",
            gridcolor="rgba(255,255,255,.08)",
        ),
        xaxis=dict(title="", gridcolor="rgba(255,255,255,.04)"),
        bargap=0.42,
        showlegend=False,
    )
    return fig


def _win_loss_donut(metrics):
    wins   = int(metrics.get("wins", 0) or 0)
    losses = int(metrics.get("losses", 0) or 0)
    closed = int(metrics.get("closed_trades", 0) or 0)
    breakeven = max(0, closed - wins - losses)

    labels, values, colors = [], [], []
    if wins:
        labels.append("Wins");      values.append(wins);      colors.append("#00ffa3")
    if losses:
        labels.append("Losses");    values.append(losses);    colors.append("#ff4d6d")
    if breakeven:
        labels.append("Breakeven"); values.append(breakeven); colors.append("#ffb020")

    if not values:
        labels, values, colors = ["No trades"], [1], ["rgba(255,255,255,.12)"]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(colors=colors, line=dict(color="rgba(10,12,20,.9)", width=2)),
            textinfo="label+value" if values != [1] else "none",
            textfont=dict(color="rgba(255,255,255,.85)", size=12),
            hovertemplate="<b>%{label}</b><br>%{value} trades<extra></extra>",
        )
    )

    win_rate = float(metrics.get("win_rate", 0) or 0)
    fig.update_layout(
        title=dict(text="Win / Loss Mix", font=dict(size=15, color="rgba(255,255,255,.85)"), x=0.02),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white", family="Inter, sans-serif"),
        margin=dict(l=20, r=20, t=46, b=20),
        showlegend=True,
        legend=dict(orientation="h", y=-0.08, font=dict(size=11, color="rgba(255,255,255,.65)")),
        annotations=[dict(
            text=f"{win_rate:.0f}%<br><span style='font-size:11px;color:rgba(255,255,255,.55)'>Win rate</span>",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=22, color="#00ffa3", family="Inter, sans-serif"),
        )],
    )
    return fig


def render_performance_charts(data):
    metrics = data.get("metrics", {})

    col1, col2 = st.columns([1.4, 1])
    with col1:
        st.plotly_chart(_pnl_bar_chart(metrics), use_container_width=True, config={"displayModeBar": False})
    with col2:
        st.plotly_chart(_win_loss_donut(metrics), use_container_width=True, config={"displayModeBar": False})
