import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data_prep"))

from data_query_tool import get_plant_status_snapshot


STATUS_COLORS = {
    "green": ("🟢", "#2fbf71"),
    "yellow": ("🟡", "#d39b1a"),
    "red": ("🔴", "#d54a4a"),
}


def render_plant_twin_page() -> None:
    st.header("Plant Digital Twin")
    st.caption("A color-coded inverter grid showing real-time plant health.")

    recent_days = st.slider("Status window (days)", min_value=1, max_value=90, value=14, help="How many recent days to use when classifying each inverter.")
    
    snapshot = get_plant_status_snapshot(recent_days=recent_days)
    summary = snapshot.get("summary", {})
    tiles = snapshot.get("tiles", [])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Optimal", summary.get("green", 0), help="Running normally")
    col2.metric("⚠️ Non-optimal", summary.get("yellow", 0), help="Warnings or derating")
    col3.metric("❌ Broken", summary.get("red", 0), help="Faulted or offline")
    col4.metric("📊 Total", summary.get("total", 0), help="All inverters")

    st.divider()
    st.subheader("Inverter Grid")
    
    if tiles:
        # Display inverters in a 9-column grid
        for row_idx in range(0, len(tiles), 9):
            row_tiles = tiles[row_idx:row_idx + 9]
            cols = st.columns(len(row_tiles))
            
            for col, tile in zip(cols, row_tiles):
                status = tile.get("status", "yellow")
                emoji, color = STATUS_COLORS.get(status, ("❓", "#888888"))
                inv_id = tile["inverter_id"]
                recent_errors = tile.get("recent_error_events", 0)
                
                with col:
                    # Create colored container based on status
                    if status == "green":
                        container_color = "#2fbf71"
                    elif status == "yellow":
                        container_color = "#d39b1a"
                    else:  # red
                        container_color = "#d54a4a"
                    
                    st.markdown(
                        f"""
                        <div style='
                            background: linear-gradient(135deg, {container_color}33, {container_color}66);
                            border: 2px solid {container_color};
                            border-radius: 10px;
                            padding: 15px;
                            text-align: center;
                            min-height: 120px;
                            display: flex;
                            flex-direction: column;
                            justify-content: space-between;
                            cursor: pointer;
                        ' title='{inv_id}'>
                            <div style='font-size: 2em;'>{emoji}</div>
                            <div style='font-size: 0.9em; color: #888; margin-top: 5px;'>Errors: {recent_errors}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    st.divider()
    st.subheader("Inverter Details")
    
    if tiles and "selected_inverter" in st.session_state:
        selected_id = st.session_state.selected_inverter
        selected_tile = next((t for t in tiles if t["inverter_id"] == selected_id), None)
        
        if selected_tile:
            col1, col2, col3 = st.columns(3)
            status = selected_tile.get("status", "yellow")
            emoji, _ = STATUS_COLORS.get(status, ("❓", "#888888"))
            
            col1.metric("Status", f"{emoji} {status.upper()}")
            col2.metric("Recent Errors", selected_tile.get("recent_error_events", 0))
            col3.metric("Error Code", selected_tile.get("latest_error_code") or "None")
            
            st.write(f"**Last Seen:** {selected_tile.get('last_seen') or 'n/a'}")
            st.write(f"**State:** {selected_tile.get('latest_state') or 'Unknown'}")
    else:
        st.info("Click a tile to inspect an inverter.")

    st.divider()
    st.markdown(
        """
        **How to read it**
        - 🟢 **Green (Optimal):** Inverter is running normally with no recent issues
        - 🟡 **Yellow (Non-optimal):** Warnings, derating, or some uncertainty detected
        - 🔴 **Red (Broken):** Inverter is faulted, offline, or showing sustained errors
        """
    )

