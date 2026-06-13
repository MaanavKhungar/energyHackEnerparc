"""
Live Data Query Tool — wraps the parquet/CSV files as Claude tool-use functions.

The RAG backend can register these as Claude tools so Claude can answer
precise numerical questions (e.g. "how many errors did INV 01.03.017
have in March 2023?") by running real pandas queries.

Usage (by RAG teammate):
    from data_query_tool import TOOLS, execute_tool
    # Pass TOOLS to Claude's tools= parameter
    # Call execute_tool(name, input) when Claude emits a tool_use block
"""

from pathlib import Path
import pandas as pd
import json

# Get project root directory (parent of data_prep)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "Plant A (start here)"

# ── Lazy-loaded DataFrames ─────────────────────────────────────────────────────
_errorcodes_df: pd.DataFrame | None = None
_tickets_df: dict | None = None


def _load_errorcodes() -> pd.DataFrame:
    global _errorcodes_df
    if _errorcodes_df is None:
        print("[tool] Loading errorcodes parquet...")
        df = pd.read_parquet(DATA_DIR / "3. Errorcodes" / "errorcodes.parquet")
        df.index = pd.to_datetime(df.index, errors="coerce")
        _errorcodes_df = df
    return _errorcodes_df


# Operational state values (from / Operational State columns):
#   0 = Off / Night
#   1 = Idle / Standby
#   2 = Starting up
#   3 = MPP tracking
#   4 = Feed-in / Running normally  ← healthy
#   5 = Derating (power limited)    ← degraded
#   6 = Fault / Error               ← the real fault metric

FAULT_STATE = 6  # inverter is in fault state

def _fault_count(series: pd.Series) -> int:
    """Count 5-min intervals where operational state = 6 (fault)."""
    return int((series == FAULT_STATE).sum())


def _load_tickets() -> dict:
    global _tickets_df
    if _tickets_df is None:
        path = DATA_DIR / "2. Additional Data" / "Tickets.xlsx"
        _tickets_df = {
            "2020_2026": pd.read_excel(path, sheet_name="2020-2026"),
            "2019_2020": pd.read_excel(path, sheet_name="2019-2020"),
        }
    return _tickets_df


# ── Tool implementations ──────────────────────────────────────────────────────

def query_inverter_errors(
    inverter_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    error_code: int | None = None,
) -> dict:
    """
    Return fault intervals for a specific inverter using operational state = 6 (fault).
    Also reports which error codes were active during fault periods.
    """
    df = _load_errorcodes()

    state_col = f"{inverter_id} / Operational State"
    error_col = f"{inverter_id} / Error"

    if state_col not in df.columns:
        matches = [c for c in df.columns if inverter_id.replace(" ", "") in c.replace(" ", "") and "State" in c]
        if not matches:
            return {"error": f"Inverter '{inverter_id}' not found."}
        state_col = matches[0]
        error_col = state_col.replace("Operational State", "Error")

    states = df[state_col].dropna()
    errors = df[error_col].dropna() if error_col in df.columns else pd.Series(dtype=float)

    if start_date:
        states = states[states.index >= pd.to_datetime(start_date)]
        errors = errors[errors.index >= pd.to_datetime(start_date)] if len(errors) else errors
    if end_date:
        states = states[states.index <= pd.to_datetime(end_date)]
        errors = errors[errors.index <= pd.to_datetime(end_date)] if len(errors) else errors

    fault_intervals = int((states == FAULT_STATE).sum())
    fault_hours = round(fault_intervals * 5 / 60, 1)

    # Error codes during fault periods
    if len(errors):
        fault_times = states[states == FAULT_STATE].index
        fault_errors = errors.reindex(fault_times).dropna()
        fault_errors = fault_errors[fault_errors != 0]
        top_codes = fault_errors.value_counts().head(5).to_dict()
        top_codes = {str(int(k)): int(v) for k, v in top_codes.items()}
    else:
        top_codes = {}

    if error_code is not None:
        count = int((errors == error_code).sum()) if len(errors) else 0
        return {
            "inverter": inverter_id,
            "error_code": error_code,
            "fault_intervals_with_code": count,
            "period": f"{start_date or 'start'} to {end_date or 'end'}",
        }

    return {
        "inverter": inverter_id,
        "fault_intervals": fault_intervals,
        "fault_hours": fault_hours,
        "top_error_codes_during_faults": top_codes,
        "period": f"{start_date or 'start'} to {end_date or 'end'}",
        "note": "fault_intervals = 5-min periods where operational state=6 (fault)",
    }


def compare_inverters_by_errors(
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 10,
) -> dict:
    """
    Rank all inverters by fault time using operational state = 6 (fault).
    This is the accurate fault metric — ignores sunrise/sunset status codes.
    """
    df = _load_errorcodes()
    state_cols = [c for c in df.columns if "/ Operational State" in c]

    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    counts = (df[state_cols] == FAULT_STATE).sum().sort_values(ascending=False)
    counts.index = [c.replace(" / Operational State", "") for c in counts.index]
    top = counts.head(top_n)

    return {
        "ranking": [
            {
                "inverter": inv,
                "fault_intervals": int(v),
                "fault_hours": round(int(v) * 5 / 60, 1),
            }
            for inv, v in top.items()
        ],
        "period": f"{start_date or 'all'} to {end_date or 'all'}",
        "total_inverters_checked": len(state_cols),
        "note": "Ranked by operational state=6 (fault) intervals, not raw error codes",
    }


def get_error_timeline(
    inverter_id: str,
    granularity: str = "monthly",
) -> dict:
    """
    Return a timeline of error counts for an inverter.
    granularity: "daily", "weekly", "monthly", or "yearly"
    """
    df = _load_errorcodes()
    col = f"{inverter_id} / Error"
    if col not in df.columns:
        return {"error": f"Inverter '{inverter_id}' not found"}

    series = df[col].dropna()
    non_zero = (series != 0).astype(int)

    freq_map = {"daily": "D", "weekly": "W", "monthly": "ME", "yearly": "YE"}
    freq = freq_map.get(granularity, "ME")
    resampled = non_zero.resample(freq).sum()

    # Return only non-zero periods
    timeline = {
        str(ts.date()): int(v)
        for ts, v in resampled.items()
        if v > 0
    }

    return {
        "inverter": inverter_id,
        "granularity": granularity,
        "timeline": timeline,
    }


def get_plant_downtime_events(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Return maintenance tickets / incident events in a date range.
    """
    tickets = _load_tickets()
    results = []

    df1 = tickets["2020_2026"].copy()
    if start_date:
        df1 = df1[pd.to_datetime(df1["startdate"], errors="coerce") >= pd.to_datetime(start_date)]
    if end_date:
        df1 = df1[pd.to_datetime(df1["startdate"], errors="coerce") <= pd.to_datetime(end_date)]

    for _, row in df1.iterrows():
        results.append({
            "start": str(row.get("startdate", "")),
            "end": str(row.get("enddate", "")),
            "component": str(row.get("component", "")),
            "category": str(row.get("category", "")),
        })

    df2 = tickets["2019_2020"].copy()
    if start_date:
        df2 = df2[pd.to_datetime(df2["Start Date"], errors="coerce") >= pd.to_datetime(start_date)]
    if end_date:
        df2 = df2[pd.to_datetime(df2["Start Date"], errors="coerce") <= pd.to_datetime(end_date)]

    for _, row in df2.iterrows():
        results.append({
            "start": str(row.get("Start Date", "")),
            "end": str(row.get("Datum Ende", "")),
            "component": str(row.get("Komponente", "")),
            "fault_type": str(row.get("Störungsart/ Beanstandung", "")),
            "duration_hours": str(row.get("Dauer in Stunden", "")),
            "kwp_affected": str(row.get("kWp of affected components", "")),
        })

    return {
        "events": results,
        "count": len(results),
        "period": f"{start_date or 'all'} to {end_date or 'all'}",
    }


def get_plant_status_snapshot(recent_days: int = 14) -> dict:
    """
    Build a plant-wide inverter status snapshot for a digital twin view.

    Status is derived from recent error events and operational state values:
    - green: no recent issues and running/feed-in state
    - yellow: recent warnings, derating, or sparse data
    - red: fault state or sustained recent errors
    """
    df = _load_errorcodes()

    error_cols = [c for c in df.columns if " / Error" in c]
    state_cols = {c.replace(" / Operational State", ""): c for c in df.columns if " / Operational State" in c}

    if len(df.index) == 0:
        return {"as_of": None, "recent_days": recent_days, "summary": {}, "tiles": []}

    latest_ts = pd.to_datetime(df.index.max(), errors="coerce")
    if pd.isna(latest_ts):
        cutoff = None
        recent_df = df
    else:
        cutoff = latest_ts - pd.Timedelta(days=recent_days)
        recent_df = df[df.index >= cutoff]

    tiles = []
    status_counts = {"green": 0, "yellow": 0, "red": 0}

    for error_col in error_cols:
        inverter_id = error_col.replace(" / Error", "").strip()
        error_series = recent_df[error_col].dropna()
        state_col = state_cols.get(inverter_id)
        state_series = recent_df[state_col].dropna() if state_col and state_col in recent_df.columns else pd.Series(dtype="float64")

        recent_error_events = int((error_series != 0).sum())
        latest_error_code = None
        if len(error_series) > 0:
            try:
                latest_error_code = int(error_series.iloc[-1])
            except Exception:
                latest_error_code = None

        latest_state = None
        if len(state_series) > 0:
            try:
                latest_state = int(state_series.iloc[-1])
            except Exception:
                latest_state = None

        if latest_state == 455 or recent_error_events >= 6:
            status = "red"
        elif latest_state == 381 or recent_error_events > 0 or (latest_error_code not in (None, 0)):
            status = "yellow"
        else:
            status = "green"

        status_counts[status] += 1

        last_seen = None
        if len(error_series) > 0:
            last_seen = error_series.index[-1]
        elif len(state_series) > 0:
            last_seen = state_series.index[-1]

        tiles.append(
            {
                "inverter_id": inverter_id,
                "status": status,
                "recent_error_events": recent_error_events,
                "latest_error_code": latest_error_code,
                "latest_state": latest_state,
                "last_seen": last_seen.isoformat() if hasattr(last_seen, "isoformat") else None,
            }
        )

    return {
        "as_of": latest_ts.isoformat() if hasattr(latest_ts, "isoformat") else None,
        "recent_days": recent_days,
        "cutoff": cutoff.isoformat() if hasattr(cutoff, "isoformat") else None,
        "summary": {
            "green": status_counts["green"],
            "yellow": status_counts["yellow"],
            "red": status_counts["red"],
            "total": len(tiles),
        },
        "tiles": sorted(tiles, key=lambda item: item["inverter_id"]),
    }


# ── Watt's Wrong O&M Tools ────────────────────────────────────────────────────

def analyze_revenue(zone_id: str, start_date: str, end_date: str) -> dict:
    """
    Analyze revenue losses from inverter faults in a zone.
    Returns lost kWh, euro loss, and weekly run-rate.
    """
    # Zone mapping (based on your digital_twin.py layout)
    ZONE_MAPPING = {
        "A.019": ["INV 01.01.001", "INV 01.01.002", "INV 01.01.003", "INV 01.01.004", "INV 01.01.005", "INV 01.01.006", "INV 01.01.007"],
        "A.014": ["INV 01.02.008", "INV 01.02.009", "INV 01.02.010", "INV 01.02.011", "INV 01.02.012", "INV 01.02.013", "INV 01.02.014"],
        "A.010": ["INV 01.03.015", "INV 01.03.016", "INV 01.03.017", "INV 01.03.018", "INV 01.03.019", "INV 01.03.020", "INV 01.03.021"],
        "A.007": ["INV 01.04.022", "INV 01.04.023", "INV 01.04.024", "INV 01.04.025", "INV 01.04.026", "INV 01.04.027", "INV 01.04.028"],
        "A.004": ["INV 01.05.029", "INV 01.05.030", "INV 01.05.031", "INV 01.05.032", "INV 01.05.033", "INV 01.05.034", "INV 01.05.035"],
        "B.018": ["INV 01.06.036", "INV 01.06.037", "INV 01.06.038", "INV 01.06.039", "INV 01.06.040", "INV 01.06.041", "INV 01.06.042", "INV 01.06.043"],
        "B.013": ["INV 01.07.044", "INV 01.07.045", "INV 01.07.046", "INV 01.07.047", "INV 01.07.048", "INV 01.07.049", "INV 01.07.050", "INV 01.07.051"],
        "B.009": ["INV 01.08.052", "INV 01.08.053", "INV 01.08.054", "INV 01.08.055", "INV 01.08.056", "INV 01.08.057", "INV 01.08.058", "INV 01.08.059"],
        "B.004": ["INV 01.09.060", "INV 01.09.061", "INV 01.09.062", "INV 01.09.063", "INV 01.09.064", "INV 01.09.065"]
    }

    zone_inverters = ZONE_MAPPING.get(zone_id, [])
    if not zone_inverters:
        return {"error": f"Unknown zone: {zone_id}"}

    # Calculate total fault hours across zone
    total_fault_hours = 0
    affected_inverters = 0

    for inv_id in zone_inverters:
        fault_data = query_inverter_errors(inv_id, start_date, end_date)
        if 'fault_hours' in fault_data:
            fault_hours = fault_data['fault_hours']
            if fault_hours > 0:
                total_fault_hours += fault_hours
                affected_inverters += 1

    # Revenue calculation (using your plant specs)
    inverter_kwp = 30.6  # From your digital_twin.py
    capacity_factor = 0.15  # Conservative for 24h periods

    lost_kwh = total_fault_hours * inverter_kwp * capacity_factor

    # Tariff calculation (simplified - could load from feed_in_tariffs.json)
    tariff_ct_per_kwh = 15.0  # Average tariff
    euro_loss = lost_kwh * tariff_ct_per_kwh / 100

    # Check if period hits 2022 price spike
    hit_2022_spike = ("2022" in start_date or "2022" in end_date)

    # Weekly run-rate
    import pandas as pd
    days_in_period = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days or 1
    euro_per_week = euro_loss * (7 / days_in_period)

    return {
        "zone_id": zone_id,
        "inverters_checked": len(zone_inverters),
        "affected_inverters": affected_inverters,
        "total_fault_hours": round(total_fault_hours, 1),
        "lost_kwh": round(lost_kwh, 0),
        "euro_loss": round(euro_loss, 0),
        "euro_per_week": round(euro_per_week, 0),
        "hit_2022_spike": hit_2022_spike,
        "tariff_used_ct_kwh": tariff_ct_per_kwh,
        "trace": f"Revenue: €{euro_loss:.0f} loss from {lost_kwh:.0f} kWh ({total_fault_hours:.1f}h downtime across {affected_inverters}/{len(zone_inverters)} inverters)"
    }


def score_risk(zone_id: str, start_date: str, end_date: str) -> dict:
    """
    Score technical risk 0-100 based on active error codes and severity.
    Returns severity score, risk band (red/amber/green), and active codes.
    """
    # Error criticality mapping (based on your error analysis)
    ERROR_CRITICALITY = {
        # Critical safety/hardware issues
        655379: 90, 655637: 90, 655629: 85, 655639: 80,  # Isolation faults
        851971: 95, 851969: 95,  # System errors
        983300: 85, 983296: 80,  # Unknown critical codes

        # Voltage/power issues
        655632: 75, 655633: 75, 655361: 70, 655362: 70,
        655374: 65, 655373: 65,

        # Temperature issues
        655618: 60, 655619: 60, 655620: 60, 655621: 60, 663565: 70,

        # Communication issues
        655648: 50, 655622: 55, 1048577: 45, 1048578: 45,

        # Common operational (lower severity due to frequency)
        655626: 30, 655616: 25, 655625: 35, 655624: 35,

        # DC-link issues (common, lower severity)
        655363: 20, 655364: 20, 655365: 25, 655366: 25,
        655367: 30, 655368: 35, 655369: 25, 655370: 35,
        655371: 30, 655372: 30,

        # Normal states
        4: 5, 2: 2, 1: 2, 0: 0
    }

    # Get zone inverters
    zone_mapping = {
        "A.019": ["INV 01.01.001", "INV 01.01.002", "INV 01.01.003", "INV 01.01.004", "INV 01.01.005", "INV 01.01.006", "INV 01.01.007"],
        "A.014": ["INV 01.02.008", "INV 01.02.009", "INV 01.02.010", "INV 01.02.011", "INV 01.02.012", "INV 01.02.013", "INV 01.02.014"],
        "A.010": ["INV 01.03.015", "INV 01.03.016", "INV 01.03.017", "INV 01.03.018", "INV 01.03.019", "INV 01.03.020", "INV 01.03.021"],
        "A.007": ["INV 01.04.022", "INV 01.04.023", "INV 01.04.024", "INV 01.04.025", "INV 01.04.026", "INV 01.04.027", "INV 01.04.028"],
        "A.004": ["INV 01.05.029", "INV 01.05.030", "INV 01.05.031", "INV 01.05.032", "INV 01.05.033", "INV 01.05.034", "INV 01.05.035"],
        "B.018": ["INV 01.06.036", "INV 01.06.037", "INV 01.06.038", "INV 01.06.039", "INV 01.06.040", "INV 01.06.041", "INV 01.06.042", "INV 01.06.043"],
        "B.013": ["INV 01.07.044", "INV 01.07.045", "INV 01.07.046", "INV 01.07.047", "INV 01.07.048", "INV 01.07.049", "INV 01.07.050", "INV 01.07.051"],
        "B.009": ["INV 01.08.052", "INV 01.08.053", "INV 01.08.054", "INV 01.08.055", "INV 01.08.056", "INV 01.08.057", "INV 01.08.058", "INV 01.08.059"],
        "B.004": ["INV 01.09.060", "INV 01.09.061", "INV 01.09.062", "INV 01.09.063", "INV 01.09.064", "INV 01.09.065"]
    }

    zone_inverters = zone_mapping.get(zone_id, [])
    if not zone_inverters:
        return {"error": f"Unknown zone: {zone_id}"}

    # Calculate risk score
    total_severity = 0
    all_active_codes = set()
    affected_inverters = 0

    for inv_id in zone_inverters:
        fault_data = query_inverter_errors(inv_id, start_date, end_date)
        if 'top_error_codes_during_faults' in fault_data:
            error_codes = fault_data['top_error_codes_during_faults']
            if error_codes:
                affected_inverters += 1
                for code_str, frequency in error_codes.items():
                    try:
                        code = int(code_str)
                        all_active_codes.add(code)
                        criticality = ERROR_CRITICALITY.get(code, 40)  # Default medium
                        # Weight by frequency and normalize
                        total_severity += criticality * min(frequency / 10, 1.0)
                    except ValueError:
                        continue

    # Normalize severity to 0-100
    severity_0_100 = min(total_severity / len(zone_inverters), 100)

    # Determine band
    if severity_0_100 >= 70:
        band = "red"
    elif severity_0_100 >= 40:
        band = "amber"
    else:
        band = "green"

    # Simple trend analysis (could be enhanced)
    trend = "stable"  # Would need time-series analysis to determine worsening/improving

    formula = "Σ(criticality × frequency_weight) per inverter, normalized to 0-100"

    return {
        "zone_id": zone_id,
        "severity_0_100": round(severity_0_100, 1),
        "band": band,
        "active_codes": sorted(list(all_active_codes)),
        "affected_inverters": affected_inverters,
        "total_inverters": len(zone_inverters),
        "trend": trend,
        "formula": formula,
        "trace": f"Risk: {severity_0_100:.1f}/100 severity ({band}), {len(all_active_codes)} error types active across {affected_inverters}/{len(zone_inverters)} inverters"
    }


def check_crew(start_date: str, end_date: str, faulted_inverters: int = 0) -> dict:
    """
    Check field crew capacity for a given maintenance window.

    Returns a weekly capacity breakdown:
      - gross capacity (technician-hours per week)
      - already allocated to routine work
      - free capacity available for reactive faults
      - hours estimated to fix current faults
      - utilisation % so the agent can judge urgency

    MOCK implementation — integrate with real scheduling system.
    Task time estimates (industry standard for utility-scale PV):
      - Inspection/diagnosis:     1.5h per inverter
      - Component swap (minor):   3h per inverter
      - Board/hardware replace:   5h per inverter
    We use 3h as a conservative default for "unknown fault type".
    """
    from datetime import datetime, timedelta

    start = datetime.fromisoformat(start_date)
    end   = datetime.fromisoformat(end_date)

    days_in_window = (end - start).days + 1
    weeks_in_window = max(days_in_window / 7, 1)

    working_days = sum(
        1 for i in range(days_in_window)
        if (start + timedelta(days=i)).weekday() < 5
    )

    # ── Capacity model (mock — replace with real HR/scheduling data) ──
    technicians       = 2
    hours_per_day     = 8
    gross_weekly_h    = technicians * 5 * hours_per_day   # 80h/week for 2 techs

    # Routine allocation: ~30% of capacity goes to scheduled preventive maintenance
    routine_pct       = 0.30
    routine_weekly_h  = round(gross_weekly_h * routine_pct)
    free_weekly_h     = gross_weekly_h - routine_weekly_h

    # Scale to the actual window
    gross_h   = round(gross_weekly_h   * weeks_in_window)
    routine_h = round(routine_weekly_h * weeks_in_window)
    free_h    = round(free_weekly_h    * weeks_in_window)

    # Estimate hours needed for current faults (3h per inverter, default)
    hours_per_inverter  = 3
    hours_needed        = faulted_inverters * hours_per_inverter
    utilisation_pct     = round(min(hours_needed / max(free_h, 1) * 100, 200))
    can_handle          = free_h // hours_per_inverter

    # Urgency signal based on utilisation
    if utilisation_pct == 0:
        urgency = "no_action"
    elif utilisation_pct <= 50:
        urgency = "routine"
    elif utilisation_pct <= 100:
        urgency = "prioritise"
    else:
        urgency = "overloaded"  # faults exceed free capacity → escalate or defer

    # Always compute next slot from today, not from analysis start date
    today = datetime.today()
    soonest_slot = None
    for i in range(1, 14):
        d = today + timedelta(days=i)
        if d.weekday() < 5:
            soonest_slot = d.strftime("%Y-%m-%d")
            break

    return {
        "mock": True,
        "technicians": technicians,
        "working_days_in_window": working_days,
        "capacity": {
            "gross_hours":   gross_h,
            "routine_hours": routine_h,
            "free_hours":    free_h,
            "gross_weekly":  gross_weekly_h,
            "free_weekly":   free_weekly_h,
        },
        "fault_demand": {
            "faulted_inverters":  faulted_inverters,
            "hours_needed":       hours_needed,
            "hours_per_inverter": hours_per_inverter,
            "can_handle":         can_handle,
            "utilisation_pct":    utilisation_pct,
            "urgency":            urgency,
        },
        "available_crew": f"{technicians} technicians · {free_h}h free",
        "soonest_slot": soonest_slot or "No slots",
        "note": "MOCK DATA — integrate with real crew scheduling system",
        "trace": (
            f"Capacity: {free_h}h free of {gross_h}h gross ({routine_h}h routine). "
            f"Fault demand: {faulted_inverters} inverters × {hours_per_inverter}h = {hours_needed}h needed. "
            f"Utilisation: {utilisation_pct}% ({urgency})"
        ),
    }


# ── Claude Tool Definitions ───────────────────────────────────────────────────

TOOLS = [
    {
        "name": "query_inverter_errors",
        "description": (
            "Query error counts for a specific inverter. "
            "Call this when the user asks about faults, errors, or problems "
            "for a specific inverter ID like 'INV 01.03.017'. "
            "Can filter by date range or specific error code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "inverter_id": {
                    "type": "string",
                    "description": "Inverter ID, e.g. 'INV 01.03.017' or 'INV 01.01.001'",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date filter YYYY-MM-DD (optional)",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date filter YYYY-MM-DD (optional)",
                },
                "error_code": {
                    "type": "integer",
                    "description": "Specific error code to count (optional)",
                },
            },
            "required": ["inverter_id"],
        },
    },
    {
        "name": "compare_inverters_by_errors",
        "description": (
            "Rank all inverters by number of error events. "
            "Call this when the user asks which inverters have the most problems, "
            "or wants a ranking/comparison of plant performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD (optional)"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD (optional)"},
                "top_n": {
                    "type": "integer",
                    "description": "How many inverters to return (default 10)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_error_timeline",
        "description": (
            "Get a time-series of error counts for an inverter. "
            "Call this when the user asks about trends, patterns over time, "
            "or when errors occurred historically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "inverter_id": {
                    "type": "string",
                    "description": "Inverter ID, e.g. 'INV 01.03.017'",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly", "yearly"],
                    "description": "Time aggregation level (default: monthly)",
                },
            },
            "required": ["inverter_id"],
        },
    },
    {
        "name": "get_plant_downtime_events",
        "description": (
            "Return maintenance tickets and downtime incidents. "
            "Call this when the user asks about outages, maintenance, "
            "shutdowns, or incident history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD (optional)"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_revenue",
        "description": (
            "Analyze revenue losses from inverter faults in a zone. "
            "Returns financial impact including lost kWh, euro losses, and weekly run-rate. "
            "Use when assessing economic impact of downtime or maintenance decisions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone identifier (A.019, A.014, A.010, A.007, A.004, B.018, B.013, B.009, B.004)",
                },
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["zone_id", "start_date", "end_date"],
        },
    },
    {
        "name": "score_risk",
        "description": (
            "Score technical risk 0-100 based on active error codes and severity. "
            "Returns risk band (red/amber/green), severity score, and active error codes. "
            "Use when assessing technical criticality and maintenance urgency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone identifier (A.019, A.014, A.010, A.007, A.004, B.018, B.013, B.009, B.004)",
                },
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["zone_id", "start_date", "end_date"],
        },
    },
    {
        "name": "check_crew",
        "description": (
            "Check crew availability for maintenance work. "
            "Returns available crews and time slots for scheduling maintenance. "
            "MOCK implementation - clearly labeled as stub for crew scheduling integration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    },
]


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool call from Claude and return result as JSON string."""
    fn_map = {
        "query_inverter_errors": query_inverter_errors,
        "compare_inverters_by_errors": compare_inverters_by_errors,
        "get_error_timeline": get_error_timeline,
        "get_plant_downtime_events": get_plant_downtime_events,
        "analyze_revenue": analyze_revenue,
        "score_risk": score_risk,
        "check_crew": check_crew,
    }
    if name not in fn_map:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn_map[name](**tool_input)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Smoke test: compare_inverters_by_errors (top 5, 2023)...")
    result = compare_inverters_by_errors(start_date="2023-01-01", end_date="2023-12-31", top_n=5)
    print(json.dumps(result, indent=2))

    print("\nSmoke test: get_plant_downtime_events (2021)...")
    result2 = get_plant_downtime_events(start_date="2021-01-01", end_date="2021-12-31")
    print(json.dumps(result2, indent=2))
