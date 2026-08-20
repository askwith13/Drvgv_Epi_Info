"""
pages_content/section_form.py
Port of ui.R's per-section tabItem / server.R's build_section_ui().
"""
import streamlit as st

import auth
import db
import meta
import scope
import widgets


def render(section_name: str):
    user = auth.current_user()
    master = db.get_master_locations()
    if master.empty:
        st.warning("No master location list has been configured yet. Contact the admin.")
        return

    scope.init_default_location(user, master)
    state, district, block = scope.current_location()
    if not (state and district and block):
        st.info("Select a block on the Location & Status tab first.")
        return

    bkey, rec = widgets.ensure_block_loaded(state, district, block, db.load_entry)

    with st.container(border=True):
        st.markdown(f'<div class="box-title">{section_name}</div>', unsafe_allow_html=True)
        st.caption(f"Reporting for: **{block}**, {district}, {state}")
        rows = meta.FORM_FIELDS[meta.FORM_FIELDS.section == section_name]
        _render_grid(rows, bkey, rec)

    sid = meta.sec_id(section_name)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="btn-warning-wrap">', unsafe_allow_html=True)
        if st.button("💾 Save as Draft", key=f"btn_save_{sid}", width="stretch"):
            _do_save(state, district, block, bkey, "Draft")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="btn-success-wrap">', unsafe_allow_html=True)
        if st.button("✅ Submit Final", key=f"btn_submit_{sid}", width="stretch"):
            _do_save(state, district, block, bkey, "Submitted")
        st.markdown("</div>", unsafe_allow_html=True)


def _width_for(itype: str) -> int:
    if itype == "category_breakdown":
        return 12
    if itype == "ratio":
        return 6
    return 4


def _render_grid(rows, bkey, rec):
    row_items = []
    running = 0

    def flush():
        nonlocal row_items, running
        if not row_items:
            return
        cols = st.columns([w for w, _ in row_items])
        for col, (_, r) in zip(cols, row_items):
            with col:
                widgets.render_field(r, bkey, rec)
        row_items = []
        running = 0

    for _, r in rows.iterrows():
        w = _width_for(r["input_type"])
        if running + w > 12 and row_items:
            flush()
        row_items.append((w, r))
        running += w
    flush()


def _do_save(state, district, block, bkey, status):
    vals = widgets.collect_all_values(bkey)
    try:
        db.save_entry(state, district, block, vals, status, auth.current_user()["username"])
        st.session_state["_loaded_block_key"] = None
        st.success(f"Saved as '{status}' for {block}, {district}, {state}.")
    except Exception as e:  # noqa: BLE001
        st.error(f"Save failed — nothing was lost, please try again. Details: {e}")
