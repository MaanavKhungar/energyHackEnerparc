# Watt's Wrong

Watt's Wrong is a Streamlit cockpit for PV operations and maintenance. It combines a near-real-time digital twin view of Plant A with historical fault analysis, revenue impact estimates, and a Claude-powered chat assistant for asking questions about plant faults.

## What It Does

- Digital Twin: shows the current operational state of Plant A, inverter health, recent critical assets, and O&M recommendations.
- Fault Analysis: explores historical faults by date, inverter, duration, event count, and estimated revenue loss.
- Voice interaction: clicking an inverter can play a short recorded inverter voice clip.
- Chat Assistant: lets users ask natural-language questions about plant performance and fault history.
- O&M Analysis: combines revenue impact, risk scoring, and crew capacity into a maintenance recommendation.

## Tech Stack

- Python
- Streamlit for the app UI
- Plotly for interactive charts, heatmaps, and inverter maps
- Pandas and NumPy for data processing
- PyArrow for Parquet data
- OpenPyXL for Excel maintenance and tariff files
- PyMuPDF for PDF/document handling
- Anthropic Claude API for chat and O&M synthesis
- Browser HTML/JavaScript embedded in Streamlit for click-to-play audio

## Project Structure

```text
energyHackEnerparc/
  frontend/
    app.py              # Main Streamlit entry point
    digital_twin.py     # Digital Twin and O&M page
    timeline.py         # Fault Analysis page
    chat_logic.py       # Chat Assistant UI and logic
    voice_twin.py       # Compatibility wrapper for Digital Twin
    assets/
      inverter_voice.mp4
  data/
    Plant A (start here)/
      2. Additional Data/
      3. Errorcodes/
  data_prep/
    data_query_tool.py  # Revenue, risk, and crew helper functions
  watts_wrong.py        # O&M analysis agent
  requirements.txt
  .env.example
```

## Setup

Create a virtual environment and install dependencies:

```bash
cd energyHackEnerparc
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
ANTHROPIC_API_KEY=your_api_key_here
```

The Anthropic key is needed for the Chat Assistant and O&M recommendation synthesis.

## Run The App

```bash
.venv/bin/python -m streamlit run frontend/app.py
```

If port `8501` is busy, choose another port:

```bash
.venv/bin/python -m streamlit run frontend/app.py --server.port 8502
```

## Pages

### Digital Twin

The Digital Twin page focuses on current operational awareness. It shows the recent health of Plant A, highlights priority inverters, and keeps the O&M section here because this is where real-time maintenance decisions belong.

The inverter map supports click-to-play audio using the recorded file at:

```text
frontend/assets/inverter_voice.mp4
```

To replace the voice, swap this file with another browser-playable audio file, or update the `VOICE_AUDIO_FILE` path in `frontend/digital_twin.py`.

### Fault Analysis

The Fault Analysis page focuses on historical exploration. It includes:

- A date activity selector
- Heatmap colouring by fault intervals, fault hours, fault events, or estimated revenue lost
- KPI cards for the selected metric
- Plant-wide error trend
- Maintenance incident trend

This page is meant for looking back in time and comparing fault patterns across inverters.

### Chat Assistant

The Chat Assistant uses Claude to answer questions about the plant data. It is useful for quick operational questions such as which inverters had the most downtime, which error codes appeared often, or where the largest revenue impact came from.

## Data Requirements

The app expects Plant A data under:

```text
data/Plant A (start here)/
```

Important inputs include:

- `3. Errorcodes/errorcodes.parquet`
- `2. Additional Data/Tickets.xlsx`
- `2. Additional Data/feed-in-tarrifs.xlsx`

If these files are missing or moved, update the paths in the frontend and data helper modules.

## Notes

- Revenue impact is an estimate based on available tariff and fault data.
- Crew capacity in the O&M workflow is currently a lightweight operational check.
- The recorded inverter voice is intentionally hardcoded for demo reliability instead of generated live with TTS.
- Streamlit may show minor deprecation warnings for older API names; the app still runs.

