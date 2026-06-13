"""
Data Preparation Pipeline for Plant A Energy Hackathon
Converts all data files into text chunks ready for RAG ingestion.

Output:
  - data_prep/chunks/  →  JSON files, one per data source
  - data_prep/summaries/  →  pre-computed stats for fast lookup
"""

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
# Get project root directory (parent of data_prep)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "Plant A (start here)"
OUT_DIR = Path(__file__).parent
CHUNKS_DIR = OUT_DIR / "chunks"
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def save_chunks(name: str, chunks: list[dict]) -> None:
    path = CHUNKS_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(chunks, f, indent=2, default=str)
    print(f"  ✓ {name}: {len(chunks)} chunks → {path}")


# ── 1. Error Code Descriptions ────────────────────────────────────────────────

def prep_error_descriptions() -> None:
    print("\n[1] Error code descriptions...")
    df = pd.read_excel(
        DATA_DIR / "3. Errorcodes" / "errorcodes description (important).xlsx",
        sheet_name="Refu Fehlercode",
    )
    df.columns = ["component", "hex", "decimal", "description"]
    df = df.dropna(subset=["description"])

    chunks = []
    for _, row in df.iterrows():
        text = (
            f"Error code {row['hex']} (decimal: {row['decimal']}) "
            f"for component '{row['component']}': {row['description']}"
        )
        chunks.append({
            "id": f"errorcode_{row['hex']}",
            "text": text,
            "metadata": {
                "source": "error_descriptions",
                "hex_code": str(row["hex"]),
                "decimal_code": str(row["decimal"]),
                "component": str(row["component"]),
            },
        })
    save_chunks("error_descriptions", chunks)


# ── 2. System Overview ────────────────────────────────────────────────────────

def prep_system_overview() -> None:
    print("\n[2] System overview...")
    xl = pd.ExcelFile(DATA_DIR / "2. Additional Data" / "System_Overview.xlsx")
    df = xl.parse("PV plant info", header=None)

    # Row 0 is the project header, row 1 has column names
    # Extract plant-level info from row 0
    plant_info_row = df.iloc[0].dropna().tolist()

    # Re-read with proper header
    df2 = xl.parse("PV plant info", header=1)
    df2 = df2.dropna(subset=["Unnamed: 2"])  # Description column

    chunks = []

    # Plant-level summary
    try:
        total_modules = int(df.iloc[0, 11]) if pd.notna(df.iloc[0, 11]) else "unknown"
        total_kwp = float(df.iloc[0, 12]) if pd.notna(df.iloc[0, 12]) else "unknown"
        total_strings = int(df.iloc[0, 13]) if pd.notna(df.iloc[0, 13]) else "unknown"
    except (IndexError, ValueError, TypeError):
        total_modules = total_kwp = total_strings = "unknown"

    chunks.append({
        "id": "plant_overview",
        "text": (
            f"Plant A is a solar PV plant named 'Example Plant'. "
            f"Total system power: {total_kwp} kWp. "
            f"Total modules: {total_modules}. "
            f"Total strings: {total_strings}. "
            f"Module type: Module Type 1 (255W per module, Manufacturer 1). "
            f"Each inverter has 5 strings with 24 modules each (30.6 kWp per inverter)."
        ),
        "metadata": {"source": "system_overview", "type": "plant_summary"},
    })

    # Per-inverter info
    inverter_rows = df2[df2["Unnamed: 2"].str.contains("WR|INV", na=False, case=False)]
    for _, row in inverter_rows.head(70).iterrows():
        inv_id = str(row.get("Unnamed: 2", "")).strip()
        if not inv_id:
            continue
        kwp = row.get("Unnamed: 9", "unknown")
        modules = row.get("Modules: System Power", "unknown")
        location = row.get("Unnamed: 5", "unknown")
        chunks.append({
            "id": f"inverter_{inv_id.replace(' ', '_').replace('.', '')}",
            "text": (
                f"Inverter {inv_id} is located at row {location}. "
                f"Capacity: {kwp} kWp with {modules} modules."
            ),
            "metadata": {
                "source": "system_overview",
                "type": "inverter_info",
                "inverter_id": inv_id,
            },
        })

    save_chunks("system_overview", chunks)


# ── 3. Maintenance Tickets ─────────────────────────────────────────────────────

CATEGORY_TRANSLATIONS = {
    "Kommunikationsstörung": "Communication fault",
    "Netzstörung": "Grid fault",
    "MS-Wartung (intern)": "Medium-voltage maintenance (internal)",
    "Allgemeine Störung": "General fault",
    "Wechselrichter": "Inverter",
    "Trafostation": "Transformer station",
}


def translate(text: str) -> str:
    if pd.isna(text):
        return ""
    for de, en in CATEGORY_TRANSLATIONS.items():
        text = str(text).replace(de, en)
    return text


def prep_tickets() -> None:
    print("\n[3] Maintenance tickets...")
    path = DATA_DIR / "2. Additional Data" / "Tickets.xlsx"
    chunks = []

    # Sheet 2020-2026
    df1 = pd.read_excel(path, sheet_name="2020-2026")
    for i, row in df1.iterrows():
        start = row.get("startdate", "")
        end = row.get("enddate", "")
        component = row.get("component", "Plant")
        category = translate(row.get("category", ""))
        duration = ""
        if pd.notna(start) and pd.notna(end):
            try:
                dur = pd.to_datetime(end) - pd.to_datetime(start)
                duration = f" Duration: {dur}."
            except Exception:
                pass
        text = (
            f"Incident on {start}: component='{component}', "
            f"category='{category}'.{duration} Ended: {end}."
        )
        chunks.append({
            "id": f"ticket_2020_{i}",
            "text": text,
            "metadata": {
                "source": "tickets",
                "sheet": "2020-2026",
                "component": str(component),
                "category": category,
                "start": str(start),
                "end": str(end),
            },
        })

    # Sheet 2019-2020
    df2 = pd.read_excel(path, sheet_name="2019-2020")
    for i, row in df2.iterrows():
        start = row.get("Start Date", "")
        end = row.get("Datum Ende", "")
        component = translate(str(row.get("Komponente", "Plant")))
        fault_type = translate(str(row.get("Störungsart/ Beanstandung", "")))
        kwp_affected = row.get("kWp of affected components", "")
        duration_h = row.get("Dauer in Stunden", "")
        text = (
            f"Incident starting {start}: component='{component}', "
            f"fault type='{fault_type}', affected capacity={kwp_affected} kWp, "
            f"duration={duration_h} hours. Ended: {end}."
        )
        chunks.append({
            "id": f"ticket_2019_{i}",
            "text": text,
            "metadata": {
                "source": "tickets",
                "sheet": "2019-2020",
                "component": component,
                "fault_type": fault_type,
                "start": str(start),
                "end": str(end),
            },
        })

    save_chunks("tickets", chunks)


# ── 4. Feed-in Tariffs ────────────────────────────────────────────────────────

def prep_feed_in_tariffs() -> None:
    print("\n[4] Feed-in tariffs...")
    df = pd.read_excel(
        DATA_DIR / "2. Additional Data" / "feed-in-tarrifs.xlsx",
        sheet_name="feed-in-tarrifs",
        header=None,
    )

    # Row 0: dates, rows 1+: inverter tariffs
    dates = df.iloc[0, 1:].tolist()
    chunks = []

    # Summarise by year
    date_series = pd.to_datetime(dates, errors="coerce")
    years = sorted(set(d.year for d in date_series if pd.notna(d)))

    for row_idx in range(1, min(len(df), 70)):
        inv_name = str(df.iloc[row_idx, 0]).strip()
        if not inv_name or inv_name.startswith("Unnamed"):
            continue
        tariff_values = df.iloc[row_idx, 1:].tolist()
        tariff_series = pd.to_numeric(pd.Series(tariff_values), errors="coerce")

        year_summaries = []
        for year in years:
            mask = [pd.notna(d) and d.year == year for d in date_series]
            year_vals = tariff_series[mask].dropna()
            if len(year_vals) > 0:
                year_summaries.append(
                    f"{year}: min={year_vals.min():.2f}, "
                    f"max={year_vals.max():.2f}, "
                    f"avg={year_vals.mean():.2f} ct/kWh"
                )

        chunks.append({
            "id": f"tariff_{inv_name.replace(' ', '_').replace('.', '')}",
            "text": (
                f"Feed-in tariff for {inv_name} (ct/kWh): "
                + "; ".join(year_summaries)
            ),
            "metadata": {
                "source": "feed_in_tariffs",
                "inverter": inv_name,
            },
        })

    save_chunks("feed_in_tariffs", chunks)


# ── 5. Error Time-Series Statistical Summaries ────────────────────────────────

def prep_error_stats() -> None:
    """
    Pre-compute per-inverter error statistics from the parquet file.
    This avoids loading 1M rows at query time.
    """
    print("\n[5] Error statistics (this may take ~30s)...")
    parquet_path = DATA_DIR / "3. Errorcodes" / "errorcodes.parquet"
    df = pd.read_parquet(parquet_path)

    # Error columns only (every other column starting from 0)
    error_cols = [c for c in df.columns if "/ Error" in c]
    state_cols = [c for c in df.columns if "/ Operational State" in c]

    chunks = []

    # Per-inverter summary
    for ecol in error_cols:
        inv_id = ecol.replace(" / Error", "").strip()
        series = df[ecol].dropna()

        if len(series) == 0:
            continue

        total_errors = int((series != 0).sum())
        if total_errors == 0:
            continue

        # Top error codes
        top_errors = series[series != 0].value_counts().head(5)
        top_str = ", ".join(
            f"code {int(k)}: {v} times" for k, v in top_errors.items()
        )

        # Yearly breakdown (using index if datetime, otherwise skip)
        year_breakdown = ""
        if hasattr(df.index, "year"):
            yearly = (
                df[ecol]
                .dropna()
                .groupby(df.index.year)
                .apply(lambda s: int((s != 0).sum()))
            )
            year_breakdown = "; ".join(
                f"{yr}: {cnt} errors" for yr, cnt in yearly.items() if cnt > 0
            )

        chunks.append({
            "id": f"error_stats_{inv_id.replace(' ', '_').replace('.', '')}",
            "text": (
                f"Inverter {inv_id} error statistics: "
                f"total non-zero error events = {total_errors:,}. "
                f"Top error codes: {top_str}. "
                + (f"Yearly breakdown: {year_breakdown}." if year_breakdown else "")
            ),
            "metadata": {
                "source": "error_stats",
                "inverter": inv_id,
                "total_errors": total_errors,
            },
        })

    # Plant-wide summary
    total_non_null = df[error_cols].notna().sum().sum()
    total_error_events = int((df[error_cols] != 0).sum().sum())
    worst_inverters = (
        (df[error_cols] != 0)
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )
    worst_str = ", ".join(
        f"{c.replace(' / Error', '')}: {v:,}"
        for c, v in worst_inverters.items()
    )

    chunks.append({
        "id": "error_stats_plant_summary",
        "text": (
            f"Plant A overall error statistics: "
            f"Dataset spans from early 2017 to June 2026 at 5-minute intervals. "
            f"Total error events across all 65 inverters: {total_error_events:,}. "
            f"Top 10 worst inverters by error count: {worst_str}."
        ),
        "metadata": {
            "source": "error_stats",
            "type": "plant_summary",
            "total_error_events": total_error_events,
        },
    })

    save_chunks("error_stats", chunks)


# ── 6. Operational State Summaries ────────────────────────────────────────────

def prep_operational_states() -> None:
    """Summarise non-running (downtime) periods per inverter."""
    print("\n[6] Operational state summaries...")
    parquet_path = DATA_DIR / "3. Errorcodes" / "errorcodes.parquet"
    df = pd.read_parquet(parquet_path)

    state_cols = [c for c in df.columns if "/ Operational State" in c]
    chunks = []

    # State value meanings (typical for SMA/Fronius type inverters)
    STATE_LABELS = {
        0: "Off/Night",
        295: "Running/Feed-in",
        381: "Derating",
        455: "Fault",
        # add more if discovered
    }

    for scol in state_cols:
        inv_id = scol.replace(" / Operational State", "").strip()
        series = df[scol].dropna()
        if len(series) == 0:
            continue

        state_counts = series.value_counts().head(8)
        state_str = ", ".join(
            f"state {int(k)} ({STATE_LABELS.get(int(k), 'unknown')}): {v:,} intervals"
            for k, v in state_counts.items()
        )

        chunks.append({
            "id": f"opstate_{inv_id.replace(' ', '_').replace('.', '')}",
            "text": (
                f"Inverter {inv_id} operational states: {state_str}. "
                f"Total recorded intervals: {len(series):,}."
            ),
            "metadata": {
                "source": "operational_states",
                "inverter": inv_id,
            },
        })

    save_chunks("operational_states", chunks)


# ── 7. Manifest ───────────────────────────────────────────────────────────────

def write_manifest(chunk_files: list[str]) -> None:
    manifest = {
        "description": "Plant A RAG data chunks",
        "chunk_files": chunk_files,
        "instructions_for_rag_teammate": (
            "Load each JSON file. Each file contains a list of chunk dicts with keys: "
            "'id' (unique str), 'text' (embed this), 'metadata' (store for filtering). "
            "Embed 'text' field and store in ChromaDB with metadata. "
            "The pandas query tool (data_query_tool.py) can answer live numerical "
            "questions using the parquet directly."
        ),
    }
    path = OUT_DIR / "manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  ✓ Manifest → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Plant A Data Prep Pipeline")
    print("=" * 60)

    prep_error_descriptions()
    prep_system_overview()
    prep_tickets()
    prep_feed_in_tariffs()
    prep_error_stats()
    prep_operational_states()

    chunk_files = [str(p.name) for p in CHUNKS_DIR.glob("*.json")]
    write_manifest(chunk_files)

    print("\n" + "=" * 60)
    print(f"✅ Done. {len(chunk_files)} chunk files in {CHUNKS_DIR}")
    print("Hand these + data_query_tool.py to the RAG teammate.")
    print("=" * 60)
