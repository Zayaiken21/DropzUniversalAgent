import streamlit as st
import plotly.graph_objects as go

def circular_chart(title, value):

    fig = go.Figure(go.Pie(
        values=[value, 100 - value],
        hole=0.82,
        marker_colors=["#00FFA3", "#1c1f26"],
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

    st.plotly_chart(fig, use_container_width=True)

def render_winrate_charts(data):

    top = st.columns(3)

    with top[0]:
        circular_chart("Overall", data["overall"])

    with top[1]:
        circular_chart("Monthly", data["monthly"])

    with top[2]:
        circular_chart("Weekly", data["weekly"])

    bottom = st.columns(3)

    with bottom[0]:
        circular_chart("Scalping", data["scalping"])

    with bottom[1]:
        circular_chart("Momentum", data["momentum"])

    with bottom[2]:
        circular_chart("Breakout", data["breakout"])