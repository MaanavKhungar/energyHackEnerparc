import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import _load_errorcodes, _load_tickets, FAULT_STATE

BG   = "#0e1117"
GRID = "#1e2130"


def _heatmap(df: pd.DataFrame, inverters: list[str], start: datetime, end: datetime, granularity: str) -> go.Figure:
    """
    Full heatmap — inverters on Y axis, time on X axis, colour = error intensity.
    Green → yellow → orange → red scale (0 = clean, high = many faults).
    """
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq = freq_map[granularity]

    state_cols = [f"{inv} / Operational State" for inv in inverters if f"{inv} / Operational State" in df.columns]
    sub = df[state_cols]
    counts = (sub == FAULT_STATE).resample(freq).sum()
    counts.columns = [c.replace(" / Operational State", "") for c in counts.columns]

    # Reindex to only selected inverters in order
    inv_order = [inv for inv in inverters if inv in counts.columns]
    matrix = counts[inv_order].T  # shape: (inverters, time)

    # Short inverter labels: "01.01.001" → "01.001"
    short_labels = [inv.replace("INV ", "") for inv in inv_order]
    date_labels  = [str(d.date()) for d in matrix.columns]

    fig = go.Figure(go.Heatmap(
        z=matrix.values,
        x=date_labels,
        y=short_labels,
        colorscale=[
            [0.0,  "#1a2e1a"],   # deep dark green — zero errors
            [0.15, "#2fbf71"],   # bright green — very few
            [0.35, "#a8c832"],   # lime
            [0.55, "#f0c040"],   # amber
            [0.75, "#e07820"],   # orange
            [1.0,  "#d52020"],   # deep red — many errors
        ],
        colorbar=dict(
            title=dict(text="Error events", font=dict(color="#c9d1d9", size=11)),
            tickfont=dict(color="#c9d1d9"),
            bgcolor=BG,
            bordercolor=GRID,
            thickness=14,
            len=0.8,
        ),
        hovertemplate="<b>%{y}</b><br>%{x}<br>Error events: %{z:,}<extra></extra>",
        xgap=1,
        ygap=1,
    ))

    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color="#c9d1d9", family="Inter, sans-serif", size=11),
        xaxis=dict(
            showgrid=False,
            tickangle=-45,
            tickfont=dict(size=10),
            linecolor=GRID,
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=10),
            autorange="reversed",
        ),
        margin=dict(l=10, r=10, t=10, b=60),
        height=max(340, len(inv_order) * 22 + 80),
    )
    return fig


def _spark_bars(df: pd.DataFrame, inverters: list[str], granularity: str) -> go.Figure:
    """
    Plant-wide error totals over time as a gradient-filled area chart.
    """
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq = freq_map[granularity]

    error_cols = [f"{inv} / Operational State" for inv in inverters if f"{inv} / Operational State" in df.columns]
    totals = (df[error_cols] == FAULT_STATE).resample(freq).sum().sum(axis=1).reset_index()
    totals.columns = ["date", "errors"]
    totals = totals[totals["errors"] > 0]

    fig = go.Figure()

    # Filled area
    fig.add_trace(go.Scatter(
        x=totals["date"],
        y=totals["errors"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(213, 74, 74, 0.18)",
        line=dict(color="#d54a4a", width=2),
        hovertemplate="<b>%{x}</b><br>%{y:,} error events<extra></extra>",
        name="",
    ))

    # Peak markers
    if len(totals) > 0:
        peak_idx = totals["errors"].idxmax()
        peak = totals.loc[peak_idx]
        fig.add_trace(go.Scatter(
            x=[peak["date"]],
            y=[peak["errors"]],
            mode="markers+text",
            marker=dict(size=10, color="#ff6b6b", symbol="circle",
                        line=dict(color="#fff", width=1.5)),
            text=[f"  Peak: {int(peak['errors']):,}"],
            textposition="middle right",
            textfont=dict(color="#ff6b6b", size=10),
            showlegend=False,
            hoverinfo="skip",
        ))

    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color="#c9d1d9", family="Inter, sans-serif"),
        xaxis=dict(showgrid=False, linecolor=GRID, tickangle=-30, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID, zeroline=False, tickfont=dict(size=10)),
        margin=dict(l=0, r=0, t=10, b=0),
        height=220,
        showlegend=False,
    )
    return fig


def _ticket_strip(start: datetime, end: datetime) -> go.Figure:
    """Incident tickets as a horizontal event strip."""
    tickets = _load_tickets()
    events = []

    for _, row in tickets["2020_2026"].iterrows():
        ts = pd.to_datetime(row.get("startdate"), errors="coerce", utc=True)
        if pd.isna(ts):
            continue
        ts = ts.tz_localize(None) if ts.tzinfo is None else ts.tz_convert(None)
        if not (start <= ts <= end):
            continue
        cat = str(row.get("category", ""))
        events.append({"date": ts, "label": f"{row.get('component','')} · {cat}", "category": cat})

    for _, row in tickets["2019_2020"].iterrows():
        ts = pd.to_datetime(row.get("Start Date"), errors="coerce", utc=True)
        if pd.isna(ts):
            continue
        ts = ts.tz_localize(None) if ts.tzinfo is None else ts.tz_convert(None)
        if not (start <= ts <= end):
            continue
        ft = str(row.get("Störungsart/ Beanstandung", ""))
        events.append({"date": ts, "label": f"{row.get('Komponente','')} · {ft}", "category": ft})

    fig = go.Figure()

    if events:
        df_ev = pd.DataFrame(events)
        # Colour by category
        cat_colours = {
            "Netzstörung": "#4a90d9",
            "Grid fault":  "#4a90d9",
            "Kommunikationsstörung": "#f0c040",
            "Communication fault":  "#f0c040",
            "MS-Wartung (intern)":  "#2fbf71",
        }
        colours = [cat_colours.get(c, "#a78bfa") for c in df_ev["category"]]

        fig.add_trace(go.Scatter(
            x=df_ev["date"],
            y=[0.5] * len(df_ev),
            mode="markers",
            marker=dict(
                symbol="diamond",
                size=16,
                color=colours,
                line=dict(color="#fff", width=1.2),
            ),
            text=df_ev["label"],
            hovertemplate="<b>%{text}</b><br>%{x}<extra></extra>",
        ))

        # Vertical drop lines
        for _, ev in df_ev.iterrows():
            fig.add_shape(type="line",
                x0=ev["date"], x1=ev["date"], y0=0, y1=0.45,
                line=dict(color="#444", width=1, dash="dot"))

    else:
        fig.add_annotation(text="No incidents in this period",
                           xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(color="#555", size=12))

    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color="#c9d1d9"),
        xaxis=dict(showgrid=False, linecolor=GRID, range=[start, end], tickfont=dict(size=10)),
        yaxis=dict(visible=False, range=[-0.1, 1.2]),
        height=120,
        margin=dict(l=0, r=0, t=6, b=30),
        showlegend=False,
    )
    return fig


def render_timeline_page() -> None:
    st.header("Fault Timeline")
    st.caption("Error intensity heatmap across all inverters · hover for details")

    df = _load_errorcodes()
    all_inverters = sorted(set(
        c.replace(" / Error", "") for c in df.columns if "/ Error" in c
    ))

    # ── Controls ───────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        date_range = st.date_input(
            "Date range",
            value=(datetime(2023, 1, 1).date(), datetime(2023, 6, 30).date()),
            min_value=datetime(2017, 1, 1).date(),
            max_value=datetime(2026, 6, 1).date(),
        )

    with c2:
        selected_inverters = st.multiselect(
            "Inverters (all 65 if empty)",
            options=all_inverters,
            default=[],
            placeholder="Leave empty for all inverters...",
        )
        if not selected_inverters:
            selected_inverters = all_inverters

    with c3:
        granularity = st.selectbox("Granularity", ["Daily", "Weekly", "Monthly"], index=1)

    if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
        st.info("Select a start and end date.")
        return

    start = datetime.combine(date_range[0], datetime.min.time())
    end   = datetime.combine(date_range[1], datetime.max.time().replace(microsecond=0))
    df_window = df.loc[start:end]

    # ── KPI strip ──────────────────────────────────────────────────────────────
    state_cols_kpi = [f"{inv} / Operational State" for inv in selected_inverters if f"{inv} / Operational State" in df_window.columns]
    total_events  = int((df_window[state_cols_kpi] == FAULT_STATE).sum().sum())
    faulted_count = int((df_window[state_cols_kpi] == FAULT_STATE).any().sum())
    worst_inv     = (df_window[state_cols_kpi] == FAULT_STATE).sum().idxmax().replace(" / Operational State", "") if state_cols_kpi else "—"
    worst_count   = int((df_window[state_cols_kpi] == FAULT_STATE).sum().max()) if state_cols_kpi else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total fault intervals",  f"{total_events:,}", help="5-min periods in fault state")
    k2.metric("Inverters with faults",  f"{faulted_count} / {len(selected_inverters)}")
    k3.metric("Worst inverter",         worst_inv.replace("INV ", ""))
    k4.metric("Worst — fault hours",    f"{round(worst_count*5/60)}h")

    st.divider()

    # ── Heatmap ────────────────────────────────────────────────────────────────
    st.subheader("Error intensity heatmap")
    st.caption("Dark green = clean · Yellow/orange = warnings · Red = sustained faults")
    st.plotly_chart(
        _heatmap(df_window, selected_inverters, start, end, granularity),
        use_container_width=True,
    )

    st.divider()

    # ── Area chart ─────────────────────────────────────────────────────────────
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.subheader("Plant-wide error trend")
        st.plotly_chart(
            _spark_bars(df_window, selected_inverters, granularity),
            use_container_width=True,
        )
    with col_b:
        st.subheader("Legend")
        st.markdown("""
        <div style='font-size:13px; line-height:2.2'>
        🟩 <b>Clean</b> — no errors<br>
        🟨 <b>Warning</b> — sporadic<br>
        🟧 <b>Degraded</b> — recurring<br>
        🟥 <b>Fault</b> — sustained
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Ticket strip ───────────────────────────────────────────────────────────
    st.subheader("Maintenance incidents")
    st.caption("🔷 Grid fault · 🟡 Communication · 🟣 Other · 🟢 Maintenance")
    st.plotly_chart(
        _ticket_strip(start, end),
        use_container_width=True,
    )
