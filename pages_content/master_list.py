"""
pages_content/master_list.py
Port of ui.R's "master_list" tabItem (master admin only).
"""
import pandas as pd
import streamlit as st

import db


def render():
    with st.container(border=True):
        st.markdown('<div class="box-title">Manage the master list of States / Districts / Blocks</div>',
                    unsafe_allow_html=True)
        st.write(
            "The dashboard's completion percentages are calculated against this list, and it is what "
            "populates the State/District/Block dropdowns for field staff. Upload a CSV with columns "
            "`State, District, Block` (one row per block) to replace the current list."
        )
        upload = st.file_uploader("Upload master_locations.csv", type="csv", key="master_upload")
        st.markdown('<div class="btn-danger-wrap">', unsafe_allow_html=True)
        if st.button("⬆️ Replace Master List", key="btn_replace_master"):
            if upload is None:
                st.error("Choose a CSV file first.")
            else:
                try:
                    df = pd.read_csv(upload, dtype=str)
                    if not {"state", "district", "block"}.issubset({c.lower() for c in df.columns}):
                        st.error("CSV must have columns: State, District, Block")
                    else:
                        db.replace_master_locations(df)
                        st.success("Master location list updated.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Update failed. Details: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")
        current = db.get_master_locations()
        st.download_button(
            "⬇️ Download current master list",
            current.to_csv(index=False).encode("utf-8"),
            file_name="master_locations.csv", mime="text/csv",
        )
        st.dataframe(current, width="stretch", hide_index=True)
