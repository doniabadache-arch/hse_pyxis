"""
substances_app.py
=================
Streamlit interface for chemical substances database.

Usage:
    streamlit run substances_app.py
"""

import json
import streamlit as st
import pandas as pd
from pathlib import Path


# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data
def load_substances():
    """Load substances from JSON."""
    file_path = Path("data/substances_clean.json")
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_display_name(s):
    """Get display name — fallback to filename if name missing."""
    name = s.get("name")
    if name:
        return name
    filename = s.get("source_filename") or s.get("source_files", ["Unknown"])[0]
    return f"Unknown ({filename})"


# ============================================================
# APP
# ============================================================
st.set_page_config(
    page_title="Chemical Substances Database",
    page_icon="🧪",
    layout="wide"
)

st.title("🧪 Chemical Substances Database")
st.caption("ATOFINA FRT — Transport regulations (ADR / IMDG / IATA)")

# Load
substances = load_substances()

if not substances:
    st.error("❌ No substances found. Run extract_htm_v2.py first.")
    st.stop()

# Stats
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total substances", len(substances))
col2.metric("With UN", sum(1 for s in substances if s.get("un")))
col3.metric("With ADR class", sum(1 for s in substances if s.get("adr_class")))
col4.metric("With flash point", sum(1 for s in substances if s.get("flash_point_c")))

# ============================================================
# SIDEBAR — FILTERS
# ============================================================
st.sidebar.header("🔍 Filters")

# Search by name
search = st.sidebar.text_input("Search by name", "")

# Filter by ADR class
adr_classes = sorted(set(s.get("adr_class") for s in substances if s.get("adr_class")))
adr_filter = st.sidebar.multiselect("ADR class", adr_classes, default=[])

# Filter by packing group
pg_options = sorted(set(s.get("packing_group") for s in substances if s.get("packing_group")))
pg_filter = st.sidebar.multiselect("Packing group", pg_options, default=[])

# ============================================================
# APPLY FILTERS
# ============================================================
filtered = substances

if search:
    filtered = [s for s in filtered if search.lower() in get_display_name(s).lower()]

if adr_filter:
    filtered = [s for s in filtered if s.get("adr_class") in adr_filter]

if pg_filter:
    filtered = [s for s in filtered if s.get("packing_group") in pg_filter]

st.markdown(f"### 📋 {len(filtered)} substances found")

# ============================================================
# SELECT ONE SUBSTANCE
# ============================================================
if filtered:
    # Build display names list
    display_names = [get_display_name(s) for s in filtered]

    selected_name = st.selectbox("Select a substance", display_names)

    # Find the selected substance by matching display name
    selected = next(
        (s for s in filtered if get_display_name(s) == selected_name),
        None
    )

    if selected:
        st.markdown("---")
        st.header(f"📌 {get_display_name(selected)}")

        # Main info
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("UN Number", selected.get("un") or "—")
            st.metric("ADR Class", selected.get("adr_class") or "—")

        with col2:
            st.metric("Hazard ID (Kemler)", selected.get("hazard_id") or "—")
            st.metric("Packing Group", selected.get("packing_group") or "—")

        with col3:
            fp = selected.get("flash_point_c")
            st.metric("Flash Point", f"{fp} °C" if fp else "—")
            st.metric("CAS", selected.get("cas") or "—")

        # Source files
        st.markdown("### 📁 Source files")
        source_files = selected.get("source_files", [])
        if source_files:
            for sf in source_files:
                st.markdown(f"- `{sf}`")
        else:
            st.markdown("_No source files recorded._")

        # Full text (expandable)
        with st.expander("📄 Full text (raw)"):
            st.text(selected.get("full_text", "_(empty)_"))

    else:
        st.error("⚠️ Selected substance not found. Try refreshing the page.")

else:
    st.warning("No substances match the filters.")

# ============================================================
# TABLE VIEW — ALL SUBSTANCES
# ============================================================
st.markdown("---")
st.header("📊 All substances")

df_data = []
for s in substances:
    df_data.append({
        "Name": get_display_name(s),
        "UN": s.get("un") or "—",
        "ADR Class": s.get("adr_class") or "—",
        "Hazard ID": s.get("hazard_id") or "—",
        "Packing Group": s.get("packing_group") or "—",
        "Flash Point (°C)": s.get("flash_point_c") or "—",
    })

df = pd.DataFrame(df_data)
st.dataframe(df, use_container_width=True, hide_index=True)
