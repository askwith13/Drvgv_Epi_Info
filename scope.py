"""
scope.py
Location scoping for state/district/block-level users, and the persistent
State/District/Block selection (equivalent to the R app's sel_state/
sel_district/sel_block inputs, which stay mounted across tab switches).
"""
import streamlit as st


def allowed_states(user, master):
    if user["scope_type"] in ("state", "district", "block"):
        return [user["state"]]
    return sorted(master["state"].dropna().unique().tolist())


def allowed_districts(user, master, state):
    if user["scope_type"] in ("district", "block"):
        return [user["district"]]
    if not state:
        return []
    return sorted(master.loc[master.state == state, "district"].dropna().unique().tolist())


def allowed_blocks(user, master, state, district):
    if user["scope_type"] == "block":
        return [user["block"]]
    if not state or not district:
        return []
    return sorted(
        master.loc[(master.state == state) & (master.district == district), "block"].dropna().unique().tolist()
    )


def init_default_location(user, master):
    if "sel_state" in st.session_state:
        return
    states = allowed_states(user, master)
    state = states[0] if states else None
    st.session_state["sel_state"] = state
    districts = allowed_districts(user, master, state)
    district = districts[0] if districts else None
    st.session_state["sel_district"] = district
    blocks = allowed_blocks(user, master, state, district)
    st.session_state["sel_block"] = blocks[0] if blocks else None


def current_location():
    return (
        st.session_state.get("sel_state"),
        st.session_state.get("sel_district"),
        st.session_state.get("sel_block"),
    )


def safe_selectbox(label, options, key, **kwargs):
    """Guards against Streamlit's exception when a persisted session_state
    value is no longer in `options` (e.g. after State/District changes)."""
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state[key] = options[0] if options else None
    if not options:
        st.selectbox(label, options=["(none available)"], disabled=True)
        return None
    return st.selectbox(label, options=options, key=key, **kwargs)
