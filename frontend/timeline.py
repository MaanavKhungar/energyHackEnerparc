import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import _load_errorcodes, _load_tickets, FAULT_STATE

BG   = "#0e1117"
GRID = "#1e2130"
INV_KWP = 30.6
REVENUE_EUR_PER_KWH = 0.1241
DAYTIME = range(6, 20)


def _metric_matrix_by_period(
    df: pd.DataFrame,
    inverters: list[str],
    granularity: str,
    metric: str,
) -> pd.DataFrame:
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq = freq_map[granularity]

    state_cols = [f"{inv} / Operational State" for inv in inverters if f"{inv} / Operational State" in df.columns]
    sub = df[state_cols]
    fault_mask = sub == FAULT_STATE

    if metric == "Fault hours":
        matrix_df = fault_mask.resample(freq).sum() * 5 / 60
    elif metric == "Fault events":
        trips = fault_mask & ~fault_mask.shift(1, fill_value=False)
        matrix_df = trips.resample(freq).sum()
    elif metric == "Revenue lost (€)":
        daytime_faults = fault_mask[fault_mask.index.hour.isin(DAYTIME)]
        fault_hours = daytime_faults.resample(freq).sum() * 5 / 60
        matrix_df = fault_hours * INV_KWP * 0.35 * REVENUE_EUR_PER_KWH
    else:
        matrix_df = fault_mask.resample(freq).sum()

    matrix_df.columns = [c.replace(" / Operational State", "") for c in matrix_df.columns]
    return matrix_df


def _range_selector(df: pd.DataFrame, inverters: list[str]) -> go.Figure:
    state_cols = [f"{inv} / Operational State" for inv in inverters if f"{inv} / Operational State" in df.columns]
    weekly = (df[state_cols] == FAULT_STATE).sum(axis=1).resample("W").sum()

    fig = go.Figure(go.Bar(
        x=weekly.index,
        y=weekly.values,
        marker=dict(
            color=weekly.values,
            colorscale=[
                [0.0, "#1a2e1a"],
                [0.2, "#2fbf71"],
                [0.5, "#f0c040"],
                [0.8, "#e07820"],
                [1.0, "#d52020"],
            ],
            cmin=0,
            cmax=weekly.max() if len(weekly) else 1,
            line=dict(width=0),
        ),
        hovertemplate="<b>Week of %{x}</b><br>Fault intervals: %{y:,}<extra></extra>",
    ))

    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color="#c9d1d9", family="Inter, sans-serif", size=10),
        height=150,
        margin=dict(l=0, r=0, t=4, b=0),
        xaxis=dict(
            showgrid=False,
            linecolor=GRID,
            tickfont=dict(size=9),
            rangeslider=dict(
                visible=True,
                bgcolor="#0e1a2e",
                bordercolor=GRID,
                borderwidth=1,
                thickness=0.30,
            ),
            range=["2023-01-01", "2023-06-30"],
            type="date",
        ),
        yaxis=dict(showgrid=False, visible=False),
        bargap=0.05,
        showlegend=False,
        dragmode="select",
    )
    return fig


def _heatmap_red_threshold(matrix: pd.DataFrame) -> float:
    non_zero_values = matrix.values[matrix.values > 0]
    threshold = float(pd.Series(non_zero_values).quantile(0.75)) if len(non_zero_values) else 1.0
    return max(threshold, 1.0)


def _heatmap(
    df: pd.DataFrame,
    inverters: list[str],
    granularity: str,
    metric: str,
) -> go.Figure:
    """
    Full heatmap — inverters on Y axis, time on X axis, colour = error intensity.
    Green → yellow → orange → red scale (0 = clean, high = many faults).
    """
    if metric == "Fault hours":
        color_title = "Fault hours"
        hover_label = "Fault hours"
        hover_format = "%{z:.1f}"
    elif metric == "Fault events":
        color_title = "Fault events"
        hover_label = "Fault events"
        hover_format = "%{z:,}"
    elif metric == "Revenue lost (€)":
        color_title = "Revenue lost (€)"
        hover_label = "Revenue lost"
        hover_format = "€%{z:.0f}"
    else:
        color_title = "Fault intervals"
        hover_label = "Fault intervals"
        hover_format = "%{z:,}"

    matrix_df = _metric_matrix_by_period(df, inverters, granularity, metric)

    # Reindex to only selected inverters in order
    inv_order = [inv for inv in inverters if inv in matrix_df.columns]
    matrix = matrix_df[inv_order].T  # shape: (inverters, time)

    # Short inverter labels: "01.01.001" → "01.001"
    short_labels = [inv.replace("INV ", "") for inv in inv_order]
    date_labels  = [str(d.date()) for d in matrix.columns]
    color_max = _heatmap_red_threshold(matrix)
    tickvals = [0, color_max * 0.25, color_max * 0.5, color_max * 0.75, color_max]
    if metric == "Revenue lost (€)":
        ticktext = [f"€{v:.0f}" for v in tickvals[:-1]] + [f"€{color_max:.0f}+"]
    elif metric == "Fault hours":
        ticktext = [f"{v:.1f}h" for v in tickvals[:-1]] + [f"{color_max:.1f}h+"]
    else:
        ticktext = [f"{v:.0f}" for v in tickvals[:-1]] + [f"{color_max:.0f}+"]

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
        zmin=0,
        zmax=color_max,
        colorbar=dict(
            title=dict(text=color_title, font=dict(color="#c9d1d9", size=11)),
            tickfont=dict(color="#c9d1d9", size=9),
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            bgcolor=BG,
            bordercolor=GRID,
            thickness=12,
            len=0.72,
        ),
        hovertemplate=f"<b>%{{y}}</b><br>%{{x}}<br>{hover_label}: {hover_format}<extra></extra>",
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
            tickfont=dict(size=8),
            linecolor=GRID,
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=6),
            autorange="reversed",
        ),
        margin=dict(l=8, r=8, t=4, b=42),
        height=430,
    )
    return fig


def _metric_totals_by_inverter(
    df: pd.DataFrame,
    inverters: list[str],
    metric: str,
) -> pd.Series:
    state_cols = [f"{inv} / Operational State" for inv in inverters if f"{inv} / Operational State" in df.columns]
    if not state_cols:
        return pd.Series(dtype="float64")

    fault_mask = df[state_cols] == FAULT_STATE
    labels = [c.replace(" / Operational State", "") for c in state_cols]

    if metric == "Fault hours":
        values = fault_mask.sum() * 5 / 60
    elif metric == "Fault events":
        values = (fault_mask & ~fault_mask.shift(1, fill_value=False)).sum()
    elif metric == "Revenue lost (€)":
        daytime_faults = fault_mask[fault_mask.index.hour.isin(DAYTIME)]
        values = daytime_faults.sum() * 5 / 60 * INV_KWP * 0.35 * REVENUE_EUR_PER_KWH
    else:
        values = fault_mask.sum()

    values.index = labels
    return values.astype(float)


def _metric_label(metric: str) -> str:
    return {
        "Fault hours": "fault hours",
        "Fault events": "fault events",
        "Revenue lost (€)": "revenue lost",
        "Fault intervals": "fault intervals",
    }.get(metric, metric.lower())


def _format_metric_value(value: float, metric: str) -> str:
    if metric == "Revenue lost (€)":
        return f"€{value:,.0f}"
    if metric == "Fault hours":
        return f"{value:,.1f}h"
    return f"{value:,.0f}"


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
    st.header("Fault Analysis")
    st.caption("Historical fault investigation across time, inverters, revenue impact, and incidents.")

    df = _load_errorcodes()
    all_inverters = sorted(set(
        c.replace(" / Error", "") for c in df.columns if "/ Error" in c
    ))

    # ── Controls ───────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1.4, 2.4, 1])

    with c1:
        heatmap_metric = st.selectbox(
            "Colour heatmap by",
            ["Fault intervals", "Fault hours", "Fault events", "Revenue lost (€)"],
            help=(
                "Fault intervals = 5-minute fault states · "
                "Fault hours = downtime duration · "
                "Fault events = trips into fault · "
                "Revenue lost = rough daytime impact"
            ),
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
        granularity = st.selectbox("Granularity", ["Daily", "Weekly", "Monthly"], index=0)

    st.markdown(
        "<div style='font-size:13px;color:#6b7a99;margin:2px 0 0'>"
        "<b style='color:#c9d1d9'>Date window</b> · drag/select on the activity bar to inspect a period"
        "</div>",
        unsafe_allow_html=True,
    )
    range_event = st.plotly_chart(
        _range_selector(df, selected_inverters),
        use_container_width=True,
        on_select="rerun",
        key="fault_analysis_range",
    )

    start = pd.Timestamp("2023-01-01")
    end = pd.Timestamp("2023-06-30 23:59:59")
    try:
        sel = range_event.get("selection", {})
        if sel and sel.get("points"):
            xs = [p["x"] for p in sel["points"]]
            if xs:
                start = pd.Timestamp(min(xs))
                end = pd.Timestamp(max(xs))
    except Exception:
        pass

    st.markdown(
        f"<div style='font-size:12px;color:#6b7a99;margin:-8px 0 4px'>Selected: "
        f"<b style='color:#c9d1d9'>{start.strftime('%d %b %Y')}</b> to "
        f"<b style='color:#c9d1d9'>{end.strftime('%d %b %Y')}</b></div>",
        unsafe_allow_html=True,
    )
    df_window = df.loc[start:end]

    # ── KPI strip ──────────────────────────────────────────────────────────────
    metric_totals = _metric_totals_by_inverter(df_window, selected_inverters, heatmap_metric)
    heatmap_matrix = _metric_matrix_by_period(df_window, selected_inverters, granularity, heatmap_metric)
    red_threshold = _heatmap_red_threshold(heatmap_matrix)
    total_value = float(metric_totals.sum()) if len(metric_totals) else 0
    worst_inv = metric_totals.idxmax() if len(metric_totals) else "—"
    worst_value = float(metric_totals.max()) if len(metric_totals) else 0
    metric_label = _metric_label(heatmap_metric)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Total {metric_label}", _format_metric_value(total_value, heatmap_metric))
    k2.metric("Red threshold", _format_metric_value(red_threshold, heatmap_metric), help="Cells at or above this value are in the top 25% and saturate red.")
    k3.metric("Worst inverter", worst_inv.replace("INV ", ""))
    k4.metric(f"Worst — {metric_label}", _format_metric_value(worst_value, heatmap_metric))

    # ── Heatmap ────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:13px;color:#6b7a99;margin:4px 0 2px'>"
        f"<b style='color:#c9d1d9'>Error intensity heatmap</b> · "
        f"Dark green = clean · Yellow/orange = elevated · Red = top 25% {heatmap_metric.lower()}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        _heatmap(df_window, selected_inverters, granularity, heatmap_metric),
        use_container_width=True,
    )

    st.divider()

    # ── Area chart ─────────────────────────────────────────────────────────────
    st.subheader("Plant-wide error trend")
    st.plotly_chart(
        _spark_bars(df_window, selected_inverters, granularity),
        use_container_width=True,
    )

    st.divider()

    # ── Ticket strip ───────────────────────────────────────────────────────────
    st.subheader("Maintenance incidents")
    st.caption("🔷 Grid fault · 🟡 Communication · 🟣 Other · 🟢 Maintenance")
    st.plotly_chart(
        _ticket_strip(start, end),
        use_container_width=True,
    )
