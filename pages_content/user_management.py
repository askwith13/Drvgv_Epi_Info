"""
pages_content/user_management.py
New (replaces shinymanager's built-in Admin panel from the R app). Master
admin only: individual add/edit, dashboard-access + active toggles, password
reset, and the unified bulk-CSV credential upload
(Username, Password, State, District, Block, DashboardAccess).
"""
import pandas as pd
import streamlit as st

import db


def render():
    with st.container(border=True):
        st.markdown('<div class="box-title">Users</div>', unsafe_allow_html=True)
        users = db.list_users()
        st.dataframe(users, width="stretch", hide_index=True)

        if not users.empty:
            st.markdown("#### Edit a user")
            uname = st.selectbox("Username", users["username"].tolist(), key="um_edit_user")
            row = users.loc[users.username == uname].iloc[0]
            c1, c2, c3 = st.columns(3)
            with c1:
                dash = st.checkbox("Dashboard access", value=bool(row["dashboard_access"]), key="um_dash",
                                    disabled=bool(row["is_master_admin"]))
            with c2:
                active = st.checkbox("Active", value=bool(row["active"]), key="um_active",
                                      disabled=bool(row["is_master_admin"]))
            with c3:
                new_pw = st.text_input("Reset password to", key="um_new_pw", type="password")
            b1, _, b3 = st.columns(3)
            with b1:
                if st.button("Save access changes", key="um_save_access"):
                    db.set_dashboard_access(uname, dash)
                    db.set_active(uname, active)
                    st.success(f"Updated {uname}.")
                    st.rerun()
            with b3:
                if st.button("Reset password", key="um_reset_pw"):
                    if not new_pw:
                        st.error("Enter a new password first.")
                    else:
                        db.reset_password(uname, new_pw)
                        st.success(f"Password reset for {uname}.")

    with st.container(border=True):
        st.markdown('<div class="box-title">Add a single user</div>', unsafe_allow_html=True)
        master = db.get_master_locations()
        c1, c2 = st.columns(2)
        with c1:
            new_username = st.text_input("Username", key="um_new_username")
            new_password = st.text_input("Password", key="um_new_password", type="password")
            scope_choice = st.selectbox("Scope", ["state", "district", "block"], key="um_new_scope")
        with c2:
            states = sorted(master.state.dropna().unique().tolist()) if not master.empty else []
            state = st.selectbox("State", states, key="um_new_state") if states else None
            district = None
            block = None
            if scope_choice in ("district", "block") and state:
                districts = sorted(master.loc[master.state == state, "district"].dropna().unique().tolist())
                district = st.selectbox("District", districts, key="um_new_district") if districts else None
            if scope_choice == "block" and state and district:
                blocks = sorted(
                    master.loc[(master.state == state) & (master.district == district), "block"].dropna().unique().tolist()
                )
                block = st.selectbox("Block", blocks, key="um_new_block") if blocks else None
            new_dash = st.checkbox("Grant dashboard access", key="um_new_dash", disabled=(scope_choice == "block"))
        if st.button("➕ Add user", key="um_add_user"):
            if not new_username or not new_password or not state:
                st.error("Username, password and state are required.")
            else:
                try:
                    db.upsert_user(new_username, new_password, False, scope_choice, state, district, block,
                                    dashboard_access=(new_dash and scope_choice != "block"), active=True)
                    st.success(f"User '{new_username}' added/updated.")
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not add user. Details: {e}")

    with st.container(border=True):
        st.markdown('<div class="box-title">Bulk upload credentials via CSV</div>', unsafe_allow_html=True)
        st.write(
            "Columns: `Username, Password, State, District, Block, DashboardAccess`. Leave District blank for "
            "a state-scope account, leave Block blank (District filled) for a district-scope account, or fill "
            "all three for a single block-scope account. `DashboardAccess` (TRUE/FALSE) only applies to "
            "state/district rows."
        )
        template = pd.DataFrame([
            {"Username": "ka_state_user", "Password": "ChangeMe123!", "State": "Karnataka",
             "District": "", "Block": "", "DashboardAccess": "TRUE"},
            {"Username": "gonikoppa_block_user", "Password": "ChangeMe456!", "State": "Karnataka",
             "District": "Kodagu", "Block": "GONIKOPPA", "DashboardAccess": ""},
        ])
        st.download_button("⬇️ Download CSV Template", template.to_csv(index=False).encode("utf-8"),
                            file_name="user_credentials_template.csv", mime="text/csv")
        upload = st.file_uploader("Upload filled-in CSV", type="csv", key="um_bulk_csv")
        st.markdown('<div class="btn-danger-wrap">', unsafe_allow_html=True)
        if st.button("⬆️ Upload Users", key="um_bulk_upload_btn"):
            if upload is None:
                st.error("Choose a CSV file first.")
            else:
                try:
                    df = pd.read_csv(upload, dtype=str, keep_default_na=False)
                    n_ok, errors = db.bulk_upsert_users(df)
                    st.success(f"{n_ok} user(s) created/updated.")
                    if errors:
                        st.warning("\n".join(errors))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Upload failed. Details: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
