"""
pages_content/location_status.py
Port of ui.R's "loc" tabItem / server.R's record_status_ui + save handlers.
"""
import streamlit as st

import auth
import db
import scope
import widgets


def render():
    user = auth.current_user()
    master = db.get_master_locations()

    with st.container(border=True):
        st.markdown('<div class="box-title">1. Select the block you are reporting for</div>',
                     unsafe_allow_html=True)
        if master.empty:
            st.warning("No master location list has been configured yet. Contact the admin.")
            return

        scope.init_default_location(user, master)
        states = scope.allowed_states(user, master)
        districts = scope.allowed_districts(user, master, st.session_state.get("sel_state"))
        blocks = scope.allowed_blocks(user, master, st.session_state.get("sel_state"),
                                       st.session_state.get("sel_district"))

        c1, c2, c3 = st.columns(3)
        with c1:
            if user["scope_type"] == "state" or user["is_master_admin"]:
                scope.safe_selectbox("State", states, "sel_state")
            else:
                st.text_input("State", value=states[0] if states else "", disabled=True)
        with c2:
            if user["scope_type"] in ("state",) or user["is_master_admin"]:
                scope.safe_selectbox("District", districts, "sel_district")
            else:
                st.text_input("District", value=districts[0] if districts else "", disabled=True)
        with c3:
            if user["scope_type"] in ("state", "district") or user["is_master_admin"]:
                scope.safe_selectbox("Block", blocks, "sel_block")
            else:
                st.text_input("Block", value=blocks[0] if blocks else "", disabled=True)

        state, district, block = scope.current_location()
        if not (state and district and block):
            st.info("No block available for your assigned scope yet — contact the admin.")
            return

        bkey, rec = widgets.ensure_block_loaded(state, district, block, db.load_entry)

        if rec:
            badge_class = "label-success" if rec.get("status") == "Submitted" else "label-warning"
            st.markdown(
                f'<div style="margin-top:10px;"><span class="label {badge_class}">{rec.get("status")}</span>'
                f'&nbsp;&nbsp;<b>Last updated:</b> {rec.get("updated_at") or ""}'
                f'&nbsp;&nbsp;<b>By:</b> {rec.get("submitted_by") or ""}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown("*No data saved yet for this block — fill in the sections and save.*")

    with st.container(border=True):
        st.markdown('<div class="box-title box-title-info">2. Fill in each section from the menu on the left, '
                    'then save</div>', unsafe_allow_html=True)
        st.write(
            "Use the sidebar to move between the 19 thematic sections. Your entries are kept as you switch "
            "tabs. When ready, use **Save as Draft** to save your progress, or **Submit Final** once the "
            "block's data is complete and verified."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="btn-warning-wrap">', unsafe_allow_html=True)
            if st.button("💾 Save as Draft", key="btn_save_draft", width="stretch"):
                _do_save(state, district, block, bkey, "Draft")
            st.markdown("</div>", unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="btn-success-wrap">', unsafe_allow_html=True)
            if st.button("✅ Submit Final", key="btn_submit_final", width="stretch"):
                _do_save(state, district, block, bkey, "Submitted")
            st.markdown("</div>", unsafe_allow_html=True)


def _do_save(state, district, block, bkey, status):
    vals = widgets.collect_all_values(bkey)
    try:
        db.save_entry(state, district, block, vals, status, auth.current_user()["username"])
        st.session_state["_loaded_block_key"] = None  # force fresh reload next render
        st.success(f"Saved as '{status}' for {block}, {district}, {state}.")
    except Exception as e:  # noqa: BLE001
        st.error(f"Save failed — nothing was lost, please try again. Details: {e}")
