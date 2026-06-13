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
        # Parse timestamp index
        df.index = pd.to_datetime(df.index, errors="coerce")
        _errorcodes_df = df
    return _errorcodes_df


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
    Return error counts for a specific inverter, optionally filtered by date range
    and/or specific error code.

    inverter_id: e.g. "INV 01.03.017"
    start_date: "YYYY-MM-DD" or None
    end_date: "YYYY-MM-DD" or None
    error_code: integer error code or None (returns all non-zero errors)
    """
    df = _load_errorcodes()
    col = f"{inverter_id} / Error"
    if col not in df.columns:
        # Try fuzzy match
        matches = [c for c in df.columns if inverter_id.replace(" ", "") in c.replace(" ", "")]
        if not matches:
            return {"error": f"Inverter '{inverter_id}' not found. Available: {list(df.columns[:5])}..."}
        col = matches[0]

    series = df[col].dropna()

    if start_date:
        series = series[series.index >= pd.to_datetime(start_date)]
    if end_date:
        series = series[series.index <= pd.to_datetime(end_date)]

    if error_code is not None:
        count = int((series == error_code).sum())
        return {
            "inverter": inverter_id,
            "error_code": error_code,
            "count": count,
            "period": f"{start_date or 'start'} to {end_date or 'end'}",
        }
    else:
        non_zero = series[series != 0]
        top = non_zero.value_counts().head(10).to_dict()
        return {
            "inverter": inverter_id,
            "total_error_events": int(len(non_zero)),
            "top_error_codes": {str(int(k)): int(v) for k, v in top.items()},
            "period": f"{start_date or 'start'} to {end_date or 'end'}",
        }


def compare_inverters_by_errors(
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 10,
) -> dict:
    """
    Rank all inverters by number of error events in a date range.
    Returns the top_n worst performers.
    """
    df = _load_errorcodes()
    error_cols = [c for c in df.columns if "/ Error" in c]

    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    counts = (df[error_cols] != 0).sum().sort_values(ascending=False)
    top = counts.head(top_n)

    return {
        "ranking": [
            {"inverter": c.replace(" / Error", ""), "error_events": int(v)}
            for c, v in top.items()
        ],
        "period": f"{start_date or 'all'} to {end_date or 'all'}",
        "total_inverters_checked": len(error_cols),
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
]


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool call from Claude and return result as JSON string."""
    fn_map = {
        "query_inverter_errors": query_inverter_errors,
        "compare_inverters_by_errors": compare_inverters_by_errors,
        "get_error_timeline": get_error_timeline,
        "get_plant_downtime_events": get_plant_downtime_events,
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
