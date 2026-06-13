import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import _load_errorcodes, FAULT_STATE

DATA_DIR = Path("/Users/krishnamavani/Documents/Energy Hackathon/Plant A (start here)")
INV_KWP  = 30.6
DAYTIME  = range(6, 20)  # hours where production is possible

LAYOUT = [
    ("INV 01.01.001", "A.019", 0), ("INV 01.01.002", "A.019", 1),
    ("INV 01.01.003", "A.019", 2), ("INV 01.01.004", "A.019", 3),
    ("INV 01.01.005", "A.019", 4), ("INV 01.01.006", "A.019", 5),
    ("INV 01.01.007", "A.019", 6),

    ("INV 01.02.008", "A.014", 0), ("INV 01.02.009", "A.014", 1),
    ("INV 01.02.010", "A.014", 2), ("INV 01.02.011", "A.014", 3),
    ("INV 01.02.012", "A.014", 4), ("INV 01.02.013", "A.014", 5),
    ("INV 01.02.014", "A.014", 6),

    ("INV 01.03.015", "A.010", 0), ("INV 01.03.016", "A.010", 1),
    ("INV 01.03.017", "A.010", 2), ("INV 01.03.018", "A.010", 3),
    ("INV 01.03.019", "A.010", 4), ("INV 01.03.020", "A.010", 5),
    ("INV 01.03.021", "A.010", 6),

    ("INV 01.04.022", "A.007", 0), ("INV 01.04.023", "A.007", 1),
    ("INV 01.04.024", "A.007", 2), ("INV 01.04.025", "A.007", 3),
    ("INV 01.04.026", "A.007", 4), ("INV 01.04.027", "A.007", 5),
    ("INV 01.04.028", "A.007", 6),

    ("INV 01.05.029", "A.004", 0), ("INV 01.05.030", "A.004", 1),
    ("INV 01.05.031", "A.004", 2), ("INV 01.05.032", "A.004", 3),
    ("INV 01.05.033", "A.004", 4), ("INV 01.05.034", "A.004", 5),
    ("INV 01.05.035", "A.004", 6),

    ("INV 01.06.036", "B.018", 0), ("INV 01.06.037", "B.018", 1),
    ("INV 01.06.038", "B.018", 2), ("INV 01.06.039", "B.018", 3),
    ("INV 01.06.040", "B.018", 4), ("INV 01.06.041", "B.018", 5),
    ("INV 01.06.042", "B.018", 6), ("INV 01.06.043", "B.018", 7),

    ("INV 01.07.044", "B.013", 0), ("INV 01.07.045", "B.013", 1),
    ("INV 01.07.046", "B.013", 2), ("INV 01.07.047", "B.013", 3),
    ("INV 01.07.048", "B.013", 4), ("INV 01.07.049", "B.013", 5),
    ("INV 01.07.050", "B.013", 6), ("INV 01.07.051", "B.013", 7),

    ("INV 01.08.052", "B.009", 0), ("INV 01.08.053", "B.009", 1),
    ("INV 01.08.054", "B.009", 2), ("INV 01.08.055", "B.009", 3),
    ("INV 01.08.056", "B.009", 4), ("INV 01.08.057", "B.009", 5),
    ("INV 01.08.058", "B.009", 6), ("INV 01.08.059", "B.009", 7),

    ("INV 01.09.060", "B.004", 0), ("INV 01.09.061", "B.004", 1),
    ("INV 01.09.062", "B.004", 2), ("INV 01.09.063", "B.004", 3),
    ("INV 01.09.064", "B.004", 4), ("INV 01.09.065", "B.004", 5),
]

ROW_ORDER  = {"A.004": 4, "A.007": 3, "A.010": 2, "A.014": 1, "A.019": 0,
              "B.004": 8, "B.009": 7, "B.013": 6, "B.018": 5}
ZONE_LABEL = {r: ("Zone A" if r.startswith("A") else "Zone B") for r in ROW_ORDER}


# ── Metric computation ─────────────────────────────────────────────────────────

def _compute_scores(window: pd.DataFrame, metric: str) -> dict[str, float]:
    """Return a score per inverter for the chosen metric."""
    scores = {}

    # Load tariff once if needed
    tariff_avg = 0.1241  # €/kWh fallback
    if metric == "Revenue lost (€)":
        try:
            xl = pd.read_excel(
                DATA_DIR / "2. Additional Data" / "feed-in-tarrifs.xlsx",
                sheet_name="feed-in-tarrifs", header=None
            )
            dates = pd.to_datetime(xl.iloc[0, 1:], errors="coerce", utc=False)
            window_dates_mask = (dates >= window.index.min()) & (dates <= window.index.max())
        except Exception:
            xl = None

    for inv_id, _, _ in LAYOUT:
        state_col = f"{inv_id} / Operational State"
        if state_col not in window.columns:
            scores[inv_id] = 0.0
            continue

        states = window[state_col].dropna()
        fault_mask = states == FAULT_STATE

        if metric == "Fault hours":
            scores[inv_id] = fault_mask.sum() * 5 / 60

        elif metric == "Fault events (trips)":
            # Count transitions into fault state (0→6)
            trips = int((fault_mask & ~fault_mask.shift(1, fill_value=False)).sum())
            scores[inv_id] = float(trips)

        elif metric == "Revenue lost (€)":
            daytime_faults = fault_mask[fault_mask.index.hour.isin(DAYTIME)]
            daytime_hours  = daytime_faults.sum() * 5 / 60

            # Get inverter-specific tariff if available
            tariff = tariff_avg
            if xl is not None:
                inv_short = inv_id.replace("INV ", "").replace(" ", "").replace(".", "")
                for row_idx in range(1, len(xl)):
                    rname = str(xl.iloc[row_idx, 0]).replace(" ", "").replace(".", "")
                    if inv_short in rname or rname in inv_short:
                        vals = pd.to_numeric(xl.iloc[row_idx, 1:], errors="coerce")
                        if xl is not None and window_dates_mask.any():
                            vals = vals[window_dates_mask.values[:len(vals)]]
                        t = vals.dropna().mean()
                        if not pd.isna(t):
                            tariff = t / 100
                        break

            energy_lost = INV_KWP * daytime_hours * 0.35
            scores[inv_id] = round(energy_lost * tariff, 2)

    return scores


def _colour(norm: float) -> str:
    if norm == 0:        return "#1a3a1a"
    elif norm < 0.2:     return "#2fbf71"
    elif norm < 0.45:    return "#a8c832"
    elif norm < 0.7:     return "#f0c040"
    elif norm < 0.88:    return "#e07820"
    else:                return "#d52020"


def _build_spatial_fig(scores: dict, max_val: float, metric: str, unit: str) -> go.Figure:
    xs, ys, colours, texts, hovers, sizes = [], [], [], [], [], []

    for inv_id, field_row, pos in LAYOUT:
        val  = scores.get(inv_id, 0)
        norm = min(val / max(max_val, 1), 1.0)

        row_y = ROW_ORDER[field_row]
        y = row_y + (1.5 if row_y >= 5 else 0)

        xs.append(pos)
        ys.append(y)
        colours.append(_colour(norm))
        sizes.append(28 + norm * 18)
        texts.append(inv_id.replace("INV ", ""))
        hovers.append(
            f"<b>{inv_id}</b><br>"
            f"Row: {field_row} ({ZONE_LABEL[field_row]})<br>"
            f"<b>{metric}:</b> {val:,.1f} {unit}<br>"
            f"Relative severity: {norm*100:.0f}%"
        )

    fig = go.Figure()

    for field_row, row_y_base in ROW_ORDER.items():
        y = row_y_base + (1.5 if row_y_base >= 5 else 0)
        max_pos = max(p for _, fr, p in LAYOUT if fr == field_row)
        fig.add_shape(type="rect",
            x0=-0.6, x1=max_pos + 0.6, y0=y - 0.45, y1=y + 0.45,
            fillcolor="rgba(30,40,55,0.6)",
            line=dict(color="rgba(60,80,100,0.4)", width=1), layer="below")
        fig.add_annotation(x=-0.9, y=y, text=f"<b>{field_row}</b>",
            showarrow=False, font=dict(size=10, color="#6b7a99"), xanchor="right")

    fig.add_shape(type="line", x0=-1, x1=9, y0=4.7, y1=4.7,
        line=dict(color="#2a3550", width=2, dash="dash"))
    fig.add_annotation(x=8.5, y=2.2, text="<b>Zone A</b>",
        showarrow=False, font=dict(size=13, color="#4a6fa5"))
    fig.add_annotation(x=8.5, y=7.2, text="<b>Zone B</b>",
        showarrow=False, font=dict(size=13, color="#4a6fa5"))

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        marker=dict(size=sizes, color=colours, symbol="square",
                    line=dict(color="rgba(255,255,255,0.15)", width=1)),
        text=texts,
        textposition="middle center",
        textfont=dict(size=7, color="rgba(255,255,255,0.75)"),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hovers,
    ))

    fig.update_layout(
        paper_bgcolor="#0a0f1a", plot_bgcolor="#0a0f1a",
        font=dict(color="#c9d1d9", family="Inter, sans-serif"),
        xaxis=dict(visible=False, range=[-1.5, 10]),
        yaxis=dict(visible=False, range=[-0.8, 10.5], autorange="reversed"),
        margin=dict(l=60, r=20, t=20, b=20),
        height=560, showlegend=False,
    )
    return fig


def _timeline_selector(df: pd.DataFrame) -> go.Figure:
    """
    Chrome DevTools network bar style — weekly fault activity as bars.
    User drags a range selector on top to pick the analysis window.
    """
    state_cols = [c for c in df.columns if "/ Operational State" in c]
    weekly = (df[state_cols] == FAULT_STATE).sum(axis=1).resample("W").sum()

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=weekly.index,
        y=weekly.values,
        marker=dict(
            color=weekly.values,
            colorscale=[
                [0.0,  "#1a3a1a"],
                [0.2,  "#2fbf71"],
                [0.5,  "#f0c040"],
                [0.8,  "#e07820"],
                [1.0,  "#d52020"],
            ],
            cmin=0,
            cmax=weekly.max(),
            line=dict(width=0),
        ),
        hovertemplate="<b>Week of %{x}</b><br>Fault intervals: %{y:,}<extra></extra>",
    ))

    fig.update_layout(
        paper_bgcolor="#0a0f1a",
        plot_bgcolor="#0a0f1a",
        font=dict(color="#c9d1d9", family="Inter, sans-serif", size=11),
        height=180,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(
            showgrid=False,
            linecolor="#2a3550",
            tickfont=dict(size=10),
            rangeslider=dict(
                visible=True,
                bgcolor="#0e1a2e",
                bordercolor="#2a3550",
                borderwidth=1,
                thickness=0.25,
            ),
            range=["2022-01-01", "2024-01-01"],
            type="date",
        ),
        yaxis=dict(showgrid=False, visible=False),
        bargap=0.05,
        showlegend=False,
        dragmode="select",
    )
    return fig


def _legend_html() -> str:
    return """
    <div style='display:flex;gap:6px;align-items:center;font-size:12px;padding:8px 0'>
        <span style='background:#1a3a1a;width:18px;height:18px;border-radius:3px;display:inline-block'></span> None &nbsp;
        <span style='background:#2fbf71;width:18px;height:18px;border-radius:3px;display:inline-block'></span> Low &nbsp;
        <span style='background:#a8c832;width:18px;height:18px;border-radius:3px;display:inline-block'></span> Moderate &nbsp;
        <span style='background:#f0c040;width:18px;height:18px;border-radius:3px;display:inline-block'></span> High &nbsp;
        <span style='background:#e07820;width:18px;height:18px;border-radius:3px;display:inline-block'></span> Severe &nbsp;
        <span style='background:#d52020;width:18px;height:18px;border-radius:3px;display:inline-block'></span> Critical
    </div>"""


# ── Page ───────────────────────────────────────────────────────────────────────

def render_digital_twin_page() -> None:
    st.header("🌿 Plant A — Digital Twin")

    df = _load_errorcodes()

    UNITS = {
        "Fault hours":          "h",
        "Revenue lost (€)":     "€",
        "Fault events (trips)": "trips",
    }

    # ── Metric selector ────────────────────────────────────────────────────────
    metric = st.radio(
        "Colour by",
        ["Fault hours", "Revenue lost (€)", "Fault events (trips)"],
        horizontal=True,
        help=(
            "**Fault hours** — total time in fault state · maintenance priority\n\n"
            "**Revenue lost** — € lost from daytime faults · financial priority\n\n"
            "**Fault events** — number of trips · stability priority"
        ),
    )

    # ── Timeline bar (Chrome DevTools style) ───────────────────────────────────
    st.caption("📅 Drag the handles below to select your analysis window · zoom in/out to navigate")

    timeline_fig = _timeline_selector(df)
    timeline_event = st.plotly_chart(
        timeline_fig,
        use_container_width=True,
        on_select="rerun",
        key="timeline_selector",
    )

    # Parse selected range from the rangeslider / box-select
    start_dt = pd.Timestamp("2023-01-01")
    end_dt   = pd.Timestamp("2023-12-31")

    try:
        sel = timeline_event.get("selection", {})
        if sel and sel.get("box"):
            x_range = sel["box"][0].get("x", [])
            if len(x_range) == 2:
                start_dt = pd.Timestamp(x_range[0])
                end_dt   = pd.Timestamp(x_range[1])
        # Also read the xaxis range from relayout (rangeslider drag)
        elif sel and sel.get("points"):
            xs = [p["x"] for p in sel["points"]]
            if xs:
                start_dt = pd.Timestamp(min(xs))
                end_dt   = pd.Timestamp(max(xs))
    except Exception:
        pass

    # Show the selected window as a readable label
    days_selected = max((end_dt - start_dt).days, 1)
    st.markdown(
        f"<div style='font-size:13px;color:#6b7a99;padding:2px 0 8px'>Selected: "
        f"<b style='color:#c9d1d9'>{start_dt.strftime('%d %b %Y')}</b> → "
        f"<b style='color:#c9d1d9'>{end_dt.strftime('%d %b %Y')}</b> "
        f"({days_selected} days)</div>",
        unsafe_allow_html=True,
    )

    window = df.loc[start_dt:end_dt]

    with st.spinner("Computing..."):
        scores = _compute_scores(window, metric)

    max_val  = max(scores.values()) if scores else 1
    unit     = UNITS[metric]

    # ── KPIs ───────────────────────────────────────────────────────────────────
    total    = sum(scores.values())
    n_crit   = sum(1 for v in scores.values() if v / max(max_val, 1) >= 0.7)
    n_clean  = sum(1 for v in scores.values() if v == 0)
    worst    = max(scores, key=scores.get)
    worst_v  = scores[worst]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Total {unit}", f"{total:,.1f}")
    k2.metric("Critical inverters", n_crit, delta=f"{n_crit} need attention", delta_color="inverse")
    k3.metric("Clean inverters", n_clean)
    k4.metric(f"Worst — {metric}", f"{worst.replace('INV ','')}  {worst_v:,.1f}{unit}")

    # ── Caption changes with metric ────────────────────────────────────────────
    captions = {
        "Fault hours":          "Size + colour = total hours in fault state · use this to prioritise maintenance",
        "Revenue lost (€)":     "Size + colour = estimated revenue lost from daytime faults · tariff × energy lost",
        "Fault events (trips)": "Size + colour = number of times the inverter tripped into fault · indicates instability",
    }
    st.caption(captions[metric])
    st.markdown(_legend_html(), unsafe_allow_html=True)

    # ── Spatial map ────────────────────────────────────────────────────────────
    st.plotly_chart(
        _build_spatial_fig(scores, max_val, metric, unit),
        use_container_width=True,
    )

    # ── Drill-down ─────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔍 Drill into an inverter")
    inv_options = [inv for inv, _, _ in LAYOUT]
    default_idx = inv_options.index(worst) if worst in inv_options else 0

    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        selected = st.selectbox(
            "Select inverter", inv_options, index=default_idx,
            format_func=lambda x: f"{x}  ·  {scores.get(x, 0):,.1f} {unit}",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Ask chatbot →", use_container_width=True, type="primary"):
            question = (
                f"Analyse {selected} from {start_dt.strftime('%Y-%m-%d')} to "
                f"{end_dt.strftime('%Y-%m-%d')}: "
                f"what is the fault duration, top error codes, and estimated revenue impact?"
            )
            st.session_state["pending_chat_question"] = question
            st.session_state["nav_to_chat"] = True
            st.info("✅ Question queued → navigate to Chat Assistant in the sidebar")

    # ── Watt's Wrong O&M Analysis ─────────────────────────────────────────────────
    st.divider()
    st.subheader("🔧 Watt's Wrong O&M Analysis")
    st.markdown("**Zone-level maintenance decision support** — Revenue impact, technical risk, and crew availability")

    # Zone selector
    zones = list(set(zone for _, zone, _ in LAYOUT))
    zone_options = sorted(zones)

    col_zone, col_period, col_analyze = st.columns([2, 2, 1])

    with col_zone:
        selected_zone = st.selectbox(
            "Select zone for O&M analysis",
            zone_options,
            format_func=lambda x: f"Zone {x} ({len([inv for inv, zone, _ in LAYOUT if zone == x])} inverters)"
        )

    with col_period:
        analysis_days = st.selectbox(
            "Analysis period",
            [7, 14, 30],
            format_func=lambda x: f"Last {x} days",
            index=0
        )

    with col_analyze:
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_clicked = st.button("🔍 Analyze Zone", use_container_width=True, type="primary")

    if analyze_clicked:
        # Import the O&M agent
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from watts_wrong import WattsWrongAgent

        from datetime import timedelta

        # Calculate date range
        end_date = end_dt.date()
        start_date = end_date - timedelta(days=analysis_days)

        with st.spinner(f"🔍 Running O&M analysis for zone {selected_zone}..."):
            try:
                agent = WattsWrongAgent()
                result = agent.analyze_zone(selected_zone, str(start_date), str(end_date))

                # Display results
                st.success("✅ Analysis complete!")

                # Key metrics
                col1, col2, col3 = st.columns(3)

                revenue = result['tool_results']['revenue']
                risk = result['tool_results']['risk']
                crew = result['tool_results']['crew']

                with col1:
                    st.metric(
                        "Revenue Loss",
                        f"€{revenue['euro_loss']:,.0f}",
                        f"{revenue['lost_kwh']:,.0f} kWh lost"
                    )

                with col2:
                    band_colors = {"red": "🔴", "amber": "🟡", "green": "🟢"}
                    band_emoji = band_colors.get(risk['band'], "❓")
                    st.metric(
                        "Risk Score",
                        f"{risk['severity_0_100']:.0f}/100 {band_emoji}",
                        f"{len(risk['active_codes'])} error types"
                    )

                with col3:
                    st.metric(
                        "Crew Status",
                        crew['available_crew'],
                        crew['soonest_slot']
                    )
                    st.caption("🏗️ MOCK crew data")

                # Decision
                verdict = result['verdict']
                decision_colors = {
                    "do_nothing": ("🟢", "success"),
                    "monitor": ("🟡", "warning"),
                    "act": ("🔴", "error")
                }
                emoji, alert_type = decision_colors.get(verdict['decision'], ("❓", "info"))

                st.markdown("### 🎯 O&M Decision")
                getattr(st, alert_type)(
                    f"{emoji} **{verdict['decision'].upper().replace('_', ' ')}** — {verdict['reasoning']}"
                )

                if verdict.get('dissent_note'):
                    st.warning(f"⚠️ **Tension noted:** {verdict['dissent_note']}")

                # Service ticket if needed
                if verdict.get('draft_ticket'):
                    st.markdown("### 📋 Draft Service Ticket")
                    st.json(verdict['draft_ticket'])

                # Tool traces (expandable)
                with st.expander("📊 Detailed Analysis"):
                    st.markdown("**Revenue Analysis:**")
                    st.write(revenue['trace'])
                    st.json(revenue)

                    st.markdown("**Risk Assessment:**")
                    st.write(risk['trace'])
                    st.json(risk)

                    st.markdown("**Crew Check:**")
                    st.write(crew['trace'])
                    st.json(crew)

            except Exception as e:
                st.error(f"❌ Analysis failed: {str(e)}")
                st.exception(e)
