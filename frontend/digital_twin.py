import sys
import base64
import json
import mimetypes
from pathlib import Path
from datetime import timedelta

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import _load_errorcodes, FAULT_STATE

DATA_DIR = ROOT / "data" / "Plant A (start here)"
VOICE_AUDIO_FILE = ROOT / "frontend" / "assets" / "inverter_voice.mp4"
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


def _voice_audio_data_uri() -> str | None:
    if not VOICE_AUDIO_FILE.exists():
        return None

    mime_type = mimetypes.guess_type(VOICE_AUDIO_FILE.name)[0] or "audio/mpeg"
    audio_b64 = base64.b64encode(VOICE_AUDIO_FILE.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{audio_b64}"


def _build_voice_spatial_html(scores: dict, max_val: float, metric: str, unit: str) -> str:
    """Render the original Plotly spatial map and play recorded audio on click."""
    fig = _build_spatial_fig(scores, max_val, metric, unit)
    fig.update_layout(clickmode="event")
    fig_html = fig.to_html(
        include_plotlyjs=True,
        full_html=False,
        div_id="voice-spatial-plot",
        config={"displayModeBar": False, "responsive": True},
    )

    inv_ids = json.dumps([inv_id for inv_id, _, _ in LAYOUT])
    audio_src = json.dumps(_voice_audio_data_uri())

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0;
  padding: 0;
  background: #0a0f1a;
  color: #c9d1d9;
  font-family: Inter, "Segoe UI", system-ui, sans-serif;
}}
#voice-spatial-plot {{ width: 100%; height: 560px; }}
#voice-banner {{
  position: fixed;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  background: #0f172a;
  border: 1px solid #3b82f6;
  border-radius: 999px;
  color: #93c5fd;
  display: none;
  font-size: 12px;
  padding: 6px 18px;
  pointer-events: none;
  white-space: nowrap;
  z-index: 9999;
}}
</style>
</head>
<body>
{fig_html}
<audio id="voice-audio" preload="auto" src=""></audio>
<div id="voice-banner">Playing: <span id="voice-name"></span></div>
<script>
const invIds = {inv_ids};
const audioSrc = {audio_src};
const plot = document.getElementById("voice-spatial-plot");
const banner = document.getElementById("voice-banner");
const bannerName = document.getElementById("voice-name");
const audio = document.getElementById("voice-audio");

function playVoice(invId) {{
  bannerName.textContent = invId || "recorded voice";
  banner.style.display = "block";

  if (!audioSrc) {{
    bannerName.textContent = "missing " + {json.dumps(str(VOICE_AUDIO_FILE.relative_to(ROOT)))};
    return;
  }}

  audio.pause();
  audio.src = audioSrc;
  audio.currentTime = 0;
  audio.onended = () => banner.style.display = "none";
  audio.onerror = () => {{
    bannerName.textContent = "audio failed to load";
  }};
  audio.play().catch(() => {{
    bannerName.textContent = "click again to allow audio";
  }});
}}

plot.on("plotly_click", event => {{
  const point = event.points && event.points[0];
  if (!point) return;
  playVoice(invIds[point.pointIndex]);
}});
</script>
</body>
</html>"""


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
    st.header("☀️ Plant A — Digital Twin")
    st.caption("Recent operational state, inverter voice, and O&M decision support.")

    df = _load_errorcodes()

    metric = "Fault hours"
    unit = "h"
    end_dt = pd.Timestamp(df.index.max())
    start_dt = end_dt - pd.Timedelta(days=7)

    # Show the selected window as a readable label
    days_selected = max((end_dt - start_dt).days, 1)
    st.markdown(
        f"<div style='font-size:13px;color:#6b7a99;padding:2px 0 8px'>Operational window: "
        f"<b style='color:#c9d1d9'>{start_dt.strftime('%d %b %Y')}</b> → "
        f"<b style='color:#c9d1d9'>{end_dt.strftime('%d %b %Y')}</b> "
        f"({days_selected} days)</div>",
        unsafe_allow_html=True,
    )

    window = df.loc[start_dt:end_dt]

    with st.spinner("Computing..."):
        scores = _compute_scores(window, metric)

    max_val  = max(scores.values()) if scores else 1

    # ── KPIs ───────────────────────────────────────────────────────────────────
    total    = sum(scores.values())
    n_crit   = sum(1 for v in scores.values() if v / max(max_val, 1) >= 0.7)
    n_clean  = sum(1 for v in scores.values() if v == 0)
    worst    = max(scores, key=scores.get)
    worst_v  = scores[worst]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Recent fault hours", f"{total:,.1f}h")
    k2.metric("Critical inverters", n_crit, delta=f"{n_crit} need attention", delta_color="inverse")
    k3.metric("Clean inverters", n_clean)
    k4.metric("Worst inverter", worst.replace("INV ", ""))

    st.caption("Size + colour = recent operational fault load · click an inverter to hear its recorded voice")
    st.markdown(_legend_html(), unsafe_allow_html=True)

    # ── Spatial map (voice-enabled) ────────────────────────────────────────────
    components.html(
        _build_voice_spatial_html(scores, max_val, metric, unit),
        height=620,
    )

    # ── Drill-down ─────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔍 Look into an inverter")
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
                    free_weekly = crew.get("capacity", {}).get("free_weekly", 0)
                    soonest     = crew.get("soonest_slot", "—")
                    st.metric(
                        "Field Capacity",
                        f"{free_weekly}h / week",
                        f"Next slot: {soonest}",
                    )
                    st.caption("🏗️ MOCK")

                # ── O&M Decision ───────────────────────────────────────────
                verdict = result['verdict']
                decision_styles = {
                    "do_nothing": ("🟢", "#1a3a1a", "#2fbf71", "DO NOTHING"),
                    "monitor":    ("🟡", "#2e2a00", "#f0c040", "MONITOR"),
                    "act":        ("🔴", "#3a1a1a", "#d52020", "ACT NOW"),
                }
                dec = verdict.get('decision', 'monitor')
                icon, bg, border, label = decision_styles.get(dec, ("⚪", "#1a1a2e", "#888", dec.upper()))

                st.markdown("### Maintenance Decision")

                d_left, d_right = st.columns([1, 1])

                # Left — decision badge only
                with d_left:
                    st.markdown(
                        f"""<div style='
                            background:{bg}; border-left:4px solid {border};
                            border-radius:6px; padding:28px 24px; height:100%;
                            display:flex; align-items:center'>
                            <div style='font-size:18px;font-weight:700;color:{border}'>
                                {icon} {label}
                            </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                # Right — short reasoning (2-3 sentences max)
                with d_right:
                    # Trim reasoning to first 2 sentences
                    full   = verdict.get('reasoning', '')
                    import re
                    # Split on '. ' but NOT on decimal numbers like 55.1
                    sents  = [s.strip() for s in re.split(r'(?<=\D)\.\s+', full) if s.strip()]
                    sents  = [s.replace('REVENUE:','').replace('RISK:','').replace('CREW:','').strip() for s in sents]
                    sents  = [s for s in sents if s]
                    short  = ' '.join(sents[:2]) if sents else full
                    dissent = verdict.get('dissent_note', '')
                    # Trim dissent too
                    dissent_short = dissent.split('.')[0] + '.' if dissent else ''

                    st.markdown(
                        f"""<div style='
                            background:#0e1117; border:1px solid #2a2d35;
                            border-radius:6px; padding:20px 24px; height:100%'>
                            <div style='font-size:11px;color:#8b95a8;margin-bottom:8px;
                                        text-transform:uppercase;letter-spacing:0.08em'>
                                Why this decision
                            </div>
                            <p style='color:#c9d1d9;font-size:14px;line-height:1.8;margin:0 0 10px'>
                                {short}
                            </p>
                            {f'''<p style="color:#a89060;font-size:14px;line-height:1.7;
                                          border-top:1px solid #2a2d35;padding-top:8px;margin:0">
                                ⚠️ {dissent_short}
                            </p>''' if dissent_short else ''}
                        </div>""",
                        unsafe_allow_html=True,
                    )

                # Draft ticket — compact
                if verdict.get('draft_ticket'):
                    ticket = verdict['draft_ticket']
                    st.markdown(
                        f"""<div style='
                            background:#0e1a2e;border-left:4px solid #4a90d9;
                            border-radius:6px;padding:10px 16px;margin-bottom:12px;
                            color:#c9d1d9;font-size:13px'>
                            📋 <b>Draft ticket:</b> {ticket.get('title','—')}
                            · Priority: <b>{ticket.get('priority','—')}</b>
                            · Due: {ticket.get('due_date','—')}
                        </div>""",
                        unsafe_allow_html=True,
                    )

                # Detailed breakdown (expandable)
                with st.expander("📊 Detailed Analysis"):
                    c_rev, c_risk, c_crew = st.columns(3)

                    with c_rev:
                        st.markdown("**💰 Revenue**")
                        st.metric("Loss",         f"€{revenue.get('euro_loss',0):,.0f}")
                        st.metric("Energy lost",  f"{revenue.get('lost_kwh',0):,.0f} kWh")
                        st.metric("Downtime",     f"{revenue.get('total_fault_hours',0):.1f}h")
                        st.metric("Rate",         f"€{revenue.get('euro_per_week',0):.0f}/week")

                    with c_risk:
                        st.markdown("**⚠️ Risk**")
                        st.metric("Severity",     f"{risk.get('severity_0_100',0):.0f}/100")
                        st.metric("Band",         risk.get('band','—').upper())
                        st.metric("Error codes",  len(risk.get('active_codes',[])))
                        st.metric("Trend",        risk.get('trend','—'))

                    with c_crew:
                        st.markdown("**👷 Capacity**")
                        cap = crew.get('capacity', {})
                        st.metric("Free",         f"{cap.get('free_hours',0)}h")
                        st.metric("Gross",        f"{cap.get('gross_hours',0)}h")
                        st.metric("Routine alloc",f"{cap.get('routine_hours',0)}h")
                        st.metric("Next slot",    crew.get('soonest_slot','—'))

            except Exception as e:
                st.error(f"❌ Analysis failed: {str(e)}")
                st.exception(e)
