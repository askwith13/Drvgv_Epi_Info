"""
pages_content/export_data.py
Port of ui.R's "export" tabItem / build_export_workbook() download handler,
extended with scope filtering for flagged state/district users.
"""
import datetime
import io

import streamlit as st

import auth
import db
import export


def render():
    user = auth.current_user()
    with st.container(border=True):
        st.markdown('<div class="box-title">Download the complete dataset</div>', unsafe_allow_html=True)
        st.write(
            "Generates an Excel file with the same layout as the original *Block Epi Info* template, "
            "containing every block submitted or saved as draft by field staff, plus a submission-status sheet."
        )
        entries = db.get_all_entries()
        scope_note = ""
        if not user["is_master_admin"]:
            if user["scope_type"] == "state":
                entries = entries[entries.state == user["state"]] if not entries.empty else entries
                scope_note = f" (filtered to {user['state']})"
            elif user["scope_type"] == "district":
                if not entries.empty:
                    entries = entries[(entries.state == user["state"]) & (entries.district == user["district"])]
                scope_note = f" (filtered to {user['district']}, {user['state']})"

        wb = export.build_export_workbook(entries)
        buf = io.BytesIO()
        wb.save(buf)
        st.download_button(
            f"⬇️ Download Full Data (Excel){scope_note}",
            buf.getvalue(),
            file_name=f"Block_Epi_Data_Export_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
