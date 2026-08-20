"""
pages_content/dashboard.py
Port of ui.R's "dashboard" tabItem / server.R's progress/value-box/plot/
drill-down logic, extended with scope filtering for flagged state/district
users (master admin sees everything, unfiltered).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
import db
import scope


def render():
    user = auth.current_user()
    progress = db.get_progress_summary()
    by_state, overall, master, entries = (
        progress["by_state"], progress["overall"], progress["master"], progress["entries"]
    )

    if not user["is_master_admin"]:
        if user["scope_type"] == "state":
            master = master[master.state == user["state"]]
            if not entries.empty:
                entries = entries[entries.state == user["state"]]
            by_state = by_state[by_state.state == user["state"]] if not by_state.empty else by_state
        elif user["scope_type"] == "district":
            master = master[(master.state == user["state"]) & (master.district == user["district"])]
            if not entries.empty:
                entries = entries[(entries.state == user["state"]) & (entries.district == user["district"])]
            by_state = by_state[by_state.state == user["state"]] if not by_state.empty else by_state
        overall = _recompute_overall(master, entries)

    vb_cols = st.columns(4)
    boxes = [
        ("Total Blocks (target)", overall["total_blocks"] if overall else 0, "value-box-blue"),
        ("Submitted (Final)", overall["submitted"] if overall else 0, "value-box-green"),
        ("Saved as Draft", overall["draft"] if overall else 0, "value-box-yellow"),
        ("Overall % Submitted", f'{overall["pct_submitted"] if overall else 0}%', "value-box-purple"),
    ]
    for col, (label, val, css) in zip(vb_cols, boxes):
        with col:
            st.markdown(
                f'<div class="value-box {css}"><div class="vb-number">{val}</div>'
                f'<div class="vb-label">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="box-title" style="margin-top:18px;">Progress by State</div>', unsafe_allow_html=True)
    if not by_state.empty:
        fig = go.Figure()
        fig.add_bar(name="Not started", x=by_state["state"], y=by_state["not_started"], marker_color="#d9534f")
        fig.add_bar(name="Draft", x=by_state["state"], y=by_state["draft"], marker_color="#f0ad4e")
        fig.add_bar(name="Submitted", x=by_state["state"], y=by_state["submitted"], marker_color="#5cb85c")
        fig.update_layout(barmode="stack", yaxis_title="Number of blocks", xaxis_title="", height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No data in scope yet.")

    st.markdown('<div class="box-title" style="margin-top:18px;">District / Block Drill-down</div>',
                unsafe_allow_html=True)
    if master.empty:
        st.info("No master locations in scope.")
        return

    ent_cols = ["state", "district", "block", "status", "updated_at", "submitted_by"]
    ent = entries[[c for c in ent_cols if c in entries.columns]] if not entries.empty else pd.DataFrame(columns=ent_cols)
    df = master.merge(ent, on=["state", "district", "block"], how="left")
    df["status"] = df["status"].fillna("Not started")

    state_options = ["All"] + sorted(df["state"].dropna().unique().tolist())
    chosen = scope.safe_selectbox("Filter by State", state_options, "dash_state_filter")
    if chosen and chosen != "All":
        df = df[df.state == chosen]
    st.dataframe(df, width="stretch", hide_index=True)


def _recompute_overall(master: pd.DataFrame, entries: pd.DataFrame):
    if master.empty:
        return dict(total_blocks=0, submitted=0, draft=0, not_started=0, pct_submitted=0)
    if entries.empty:
        submitted = draft = 0
    else:
        merged = master.merge(entries[["state", "district", "block", "status"]],
                               on=["state", "district", "block"], how="left")
        submitted = int((merged["status"] == "Submitted").sum())
        draft = int((merged["status"] == "Draft").sum())
    total = len(master)
    return dict(
        total_blocks=total, submitted=submitted, draft=draft,
        not_started=total - submitted - draft,
        pct_submitted=round(100 * submitted / total, 1) if total else 0,
    )
