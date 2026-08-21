"""
widgets.py
Port of server.R's make_input() / build_section_ui() / collect_values().

Design note on state handling (Streamlit has no direct equivalent of Shiny's
per-session reactive `rec`/renderUI-on-block-change):
  - Every field's Streamlit widget key is scoped to the currently selected
    block via `bkey` (see block_key()).
  - When the block selection changes, seed_all_field_state() pre-populates
    st.session_state for every field across ALL 19 sections (not just the
    one being viewed) directly from the freshly loaded DB record - this is
    the Python equivalent of the R app's `outputOptions(..., suspendWhenHidden
    = FALSE)` trick, which forces every section's inputs to exist even on
    tabs the user hasn't opened yet, so a Save from any tab captures the
    whole record correctly.
  - Because those keys are pre-seeded in session_state (not passed via a
    widget's `value=`), collect_all_values() can read them at Save time
    regardless of which section is currently on screen.
"""
from __future__ import annotations

import streamlit as st

import calculations
import meta


def block_key(state: str, district: str, block: str) -> str:
    return f"{state}||{district}||{block}"


def _k(bkey: str, suffix: str) -> str:
    return f"{bkey}::{suffix}"


def _num_or_none(v):
    fv = calculations._to_float(v)
    return fv


def _str_or_none(v):
    fv = calculations._to_float(v)
    if fv is None:
        return None
    if fv == int(fv):
        return str(int(fv))
    return str(fv)


# ---------------------------------------------------------------------------
# Seed session_state for a newly-selected block from its DB record
# ---------------------------------------------------------------------------
def ensure_block_loaded(state: str, district: str, block: str, load_entry_fn):
    bkey = block_key(state, district, block)
    if st.session_state.get("_loaded_block_key") == bkey:
        return bkey, st.session_state.get("_loaded_record")

    rec = load_entry_fn(state, district, block) or {}
    st.session_state["_loaded_block_key"] = bkey
    st.session_state["_loaded_record"] = rec
    _seed_all_field_state(bkey, rec)
    return bkey, rec


def _seed_all_field_state(bkey: str, rec: dict):
    for _, row in meta.FORM_FIELDS.iterrows():
        fid = row["field_id"]
        itype = row["input_type"]
        if row["is_backend"] == "TRUE":
            continue  # field staff never edit these; nothing to seed
        if itype == "numeric" or itype in ("naat_capacity_total", "category_total",
                                            "naat_modules_reference"):
            if itype == "numeric":
                st.session_state[_k(bkey, fid)] = _num_or_none(rec.get(fid))
        elif itype == "yesno":
            v = rec.get(fid)
            st.session_state[_k(bkey, fid)] = v if v in ("Yes", "No") else ""
        elif itype in ("text",):
            st.session_state[_k(bkey, fid)] = rec.get(fid) or ""
        elif itype == "textarea":
            st.session_state[_k(bkey, fid)] = rec.get(fid) or ""
        elif itype == "multiselect":
            v = rec.get(fid) or ""
            st.session_state[_k(bkey, fid)] = v.split("; ") if v else []
            st.session_state[_k(bkey, f"{fid}_other_text")] = rec.get(f"{fid}_other_text") or ""
        elif itype == "ratio":
            st.session_state[_k(bkey, f"{fid}_num")] = _num_or_none(rec.get(f"{fid}_num"))
            st.session_state[_k(bkey, f"{fid}_den")] = _num_or_none(rec.get(f"{fid}_den"))
        elif itype == "category_breakdown":
            cfg = meta.CATEGORY_BREAKDOWN[fid]
            for cat in cfg["categories"]:
                cid = f"{fid}_cat_{meta.slugify(cat)}"
                st.session_state[_k(bkey, cid)] = _num_or_none(rec.get(cid))
            st.session_state[_k(bkey, f"{fid}_cat_other_count")] = _num_or_none(rec.get(f"{fid}_cat_other_count"))
            st.session_state[_k(bkey, f"{fid}_cat_other_text")] = rec.get(f"{fid}_cat_other_text") or ""


# ---------------------------------------------------------------------------
# Render one field
# ---------------------------------------------------------------------------
def render_field(row, bkey: str, rec: dict):
    fid = row["field_id"]

    if row["is_backend"] == "TRUE":
        _render_backend_readonly(row, rec)
        return

    if row["input_type"] == "ratio":
        _render_ratio(row, bkey)
    elif row["input_type"] == "category_breakdown":
        _render_category_breakdown(row, bkey)
    elif row["input_type"] == "category_total":
        _render_category_total(row, bkey)
    elif row["input_type"] == "naat_modules_reference":
        _render_naat_modules_reference(row, bkey)
    elif row["input_type"] == "naat_capacity_total":
        _render_naat_capacity_total(row, bkey)
    elif row["input_type"] == "numeric":
        st.number_input(_label(row), key=_k(bkey, fid), step=1.0, format="%.2f")
        _source_caption(row)
    elif row["input_type"] == "yesno":
        st.selectbox(_label(row), options=["", "Yes", "No"], key=_k(bkey, fid))
        _source_caption(row)
    elif row["input_type"] == "multiselect":
        choices = meta.get_multiselect_choices(row["field_name"])
        st.multiselect(_label(row), options=choices, key=_k(bkey, fid))
        if "Other" in choices:
            st.text_input("If you selected 'Other', please specify:",
                           key=_k(bkey, f"{fid}_other_text"))
        _source_caption(row)
    elif row["input_type"] == "textarea":
        st.text_area(_label(row), key=_k(bkey, fid), height=80)
        _source_caption(row)
    else:  # "text"
        st.text_input(_label(row), key=_k(bkey, fid))
        _source_caption(row)


def _label(row) -> str:
    return row["field_name"]


def _source_caption(row):
    if row["source"]:
        st.caption(f"ℹ️ Source: {row['source']}")
    if row["note"] and row["input_type"] not in ("ratio", "category_breakdown"):
        st.caption(row["note"])


def _render_backend_readonly(row, rec: dict):
    st.markdown(f"**{row['field_name']}**")
    st.markdown('<span class="label label-default">🔒 Provided centrally by admin — not editable here</span>',
                unsafe_allow_html=True)
    fid = row["field_id"]
    if row["input_type"] == "ratio":
        num_v = calculations._to_float(rec.get(f"{fid}_num"))
        den_v = calculations._to_float(rec.get(f"{fid}_den"))
        computed = calculations.compute_ratio_value(num_v, den_v, row["formula_type"])
        display = calculations.format_ratio_display(computed, row["formula_type"]) if computed is not None else "Admin entry"
        empty = computed is None
    else:
        v = rec.get(fid)
        empty = v is None or str(v) == ""
        display = "Admin entry" if empty else str(v)
    css = "readonly-box-empty" if empty else "readonly-box"
    st.markdown(f'<div class="{css}">{display}</div>', unsafe_allow_html=True)
    if row["source"]:
        st.caption(f"ℹ️ Source: {row['source']}")


def _render_ratio(row, bkey: str):
    fid = row["field_id"]
    st.markdown(f"**{row['field_name']}**")
    if row["source"]:
        st.caption(f"ℹ️ Source: {row['source']}")
    c1, c2 = st.columns(2)
    with c1:
        num = st.number_input(f"Numerator: {row['note'] or ''}", key=_k(bkey, f"{fid}_num"), step=1.0)
    with c2:
        den = st.number_input(f"Denominator: {row['denominator'] or ''}", key=_k(bkey, f"{fid}_den"), step=1.0)
    val = calculations.compute_ratio_value(num, den, row["formula_type"])
    st.markdown(f'<span class="calc-value">{calculations.format_ratio_display(val, row["formula_type"])}</span>',
                unsafe_allow_html=True)


def _render_category_breakdown(row, bkey: str):
    fid = row["field_id"]
    cfg = meta.CATEGORY_BREAKDOWN[fid]
    st.markdown(f"**{row['field_name']}**")
    if row["note"]:
        st.caption(row["note"])
    if row["source"]:
        st.caption(f"ℹ️ Source: {row['source']}")
    cols = st.columns(len(cfg["categories"]))
    values = []
    for col, cat in zip(cols, cfg["categories"]):
        with col:
            v = st.number_input(cat, key=_k(bkey, f"{fid}_cat_{meta.slugify(cat)}"), step=1.0, format="%.2f")
            values.append(v)
    c1, c2 = st.columns([1, 2])
    with c1:
        other_v = st.number_input("Other (count)", key=_k(bkey, f"{fid}_cat_other_count"), step=1.0, format="%.2f")
        values.append(other_v)
    with c2:
        st.text_input("Other — please specify", key=_k(bkey, f"{fid}_cat_other_text"))
    total = calculations.compute_category_total(values)
    st.markdown(f'{row["field_name"]} — Total: <span class="calc-value">{total}</span>', unsafe_allow_html=True)


def _live_value(bkey, fid):
    return st.session_state.get(_k(bkey, fid))


def _render_category_total(row, bkey: str):
    total_fid = row["field_id"]
    src_fid = meta.TOTAL_TO_BREAKDOWN[total_fid]
    cfg = meta.CATEGORY_BREAKDOWN[src_fid]
    ids = [f"{src_fid}_cat_{meta.slugify(c)}" for c in cfg["categories"]] + [f"{src_fid}_cat_other_count"]
    values = [_live_value(bkey, i) for i in ids]
    total = calculations.compute_category_total(values)
    st.markdown(f'**{row["field_name"]}**: <span class="calc-value">{total}</span>', unsafe_allow_html=True)
    st.markdown('<span class="label label-info">🧮 Auto-calculated from the breakdown above</span>',
                unsafe_allow_html=True)


def _render_naat_modules_reference(row, bkey: str):
    cfg = meta.NAAT_CAPACITY_CONFIG
    cb = calculations._to_float(_live_value(bkey, cfg["module_fields"][0])) or 0
    tn = calculations._to_float(_live_value(bkey, cfg["module_fields"][1])) or 0
    st.markdown(f'**{row["field_name"]}**: <span class="calc-value">CBNAAT: {cb:g}   +   TruNAAT: {tn:g}   =   '
                f'{cb + tn:g} total modules</span>', unsafe_allow_html=True)
    if row["note"]:
        st.caption(row["note"])
    st.markdown('<span class="label label-info">🔗 Live from Health Infrastructure section</span>',
                unsafe_allow_html=True)


def _render_naat_capacity_total(row, bkey: str):
    cfg = meta.NAAT_CAPACITY_CONFIG
    mods = [_live_value(bkey, f) for f in cfg["module_fields"]]
    shifts = _live_value(bkey, cfg["shifts_field"])
    val = calculations.compute_naat_capacity(mods, shifts, cfg)
    display = "Enter number of shifts above" if val is None else f"{val:,.0f} tests / year"
    st.markdown(f'**{row["field_name"]}**: <span class="calc-value">{display}</span>', unsafe_allow_html=True)
    if row["note"]:
        st.caption(row["note"])
    st.markdown('<span class="label label-info">🧮 Auto-calculated: modules × 6 tests × shifts × 20 days × 12 months'
                '</span>', unsafe_allow_html=True)
    if row["source"]:
        st.caption(f"ℹ️ Source: {row['source']}")


# ---------------------------------------------------------------------------
# Collect every field's current value for saving (mirrors collect_values())
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Progress tracker (% of fields filled so far, live off session_state)
# ---------------------------------------------------------------------------
# Excludes backend fields (never editable here) and read-only computed fields
# (category_total / naat_modules_reference / naat_capacity_total) - those are
# derived from other fields, not something the user directly fills in.
PROGRESS_FIELDS = meta.FORM_FIELDS.loc[
    (meta.FORM_FIELDS.is_backend != "TRUE")
    & (~meta.FORM_FIELDS.input_type.isin(
        ["category_total", "naat_modules_reference", "naat_capacity_total"]
    ))
].reset_index(drop=True)


def field_is_filled(row, bkey: str) -> bool:
    fid = row["field_id"]
    itype = row["input_type"]
    if itype == "numeric":
        return _live_value(bkey, fid) is not None
    if itype == "yesno":
        return _live_value(bkey, fid) in ("Yes", "No")
    if itype in ("text", "textarea"):
        v = _live_value(bkey, fid)
        return bool(v and str(v).strip())
    if itype == "multiselect":
        return bool(_live_value(bkey, fid))
    if itype == "ratio":
        num_v = _live_value(bkey, f"{fid}_num")
        den_v = _live_value(bkey, f"{fid}_den")
        return num_v is not None and den_v is not None
    if itype == "category_breakdown":
        cfg = meta.CATEGORY_BREAKDOWN[fid]
        ids = [f"{fid}_cat_{meta.slugify(c)}" for c in cfg["categories"]]
        ids.append(f"{fid}_cat_other_count")
        for cid in ids:
            v = calculations._to_float(_live_value(bkey, cid))
            if v is not None and v > 0:
                return True
        return False
    return False


def section_progress(section_name: str, bkey: str):
    """Returns (filled, total, pct) for one section."""
    rows = PROGRESS_FIELDS[PROGRESS_FIELDS.section == section_name]
    total = len(rows)
    if total == 0:
        return 0, 0, 0.0
    filled = sum(field_is_filled(r, bkey) for _, r in rows.iterrows())
    return filled, total, filled / total * 100.0


def overall_progress(bkey: str):
    """Returns (filled, total, pct) across every section."""
    total = len(PROGRESS_FIELDS)
    if total == 0:
        return 0, 0, 0.0
    filled = sum(field_is_filled(r, bkey) for _, r in PROGRESS_FIELDS.iterrows())
    return filled, total, filled / total * 100.0


def current_bkey():
    """The block key for whichever block is currently loaded in session_state,
    or None if no block has been selected yet this session."""
    return st.session_state.get("_loaded_block_key")


def render_progress_bar(label: str, filled: int, total: int, pct: float):
    fill_class = "progress-fill-green" if pct >= 100 else "progress-fill-blue"
    st.markdown(
        f'<div class="progress-wrap">'
        f'<div class="progress-label"><span>{label}</span>'
        f'<span>{filled} / {total} fields &middot; {pct:.0f}%</span></div>'
        f'<div class="progress-track">'
        f'<div class="progress-fill {fill_class}" style="width:{pct:.1f}%;"></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def collect_all_values(bkey: str) -> dict:
    vals = {}
    for _, row in meta.FORM_FIELDS.iterrows():
        fid = row["field_id"]
        itype = row["input_type"]
        if row["is_backend"] == "TRUE":
            continue
        if itype in ("category_total", "naat_modules_reference"):
            continue

        if itype == "naat_capacity_total":
            cfg = meta.NAAT_CAPACITY_CONFIG
            mods = [_live_value(bkey, f) for f in cfg["module_fields"]]
            shifts = _live_value(bkey, cfg["shifts_field"])
            val = calculations.compute_naat_capacity(mods, shifts, cfg)
            vals[fid] = None if val is None else _str_or_none(val)

        elif itype == "ratio":
            num_v = _live_value(bkey, f"{fid}_num")
            den_v = _live_value(bkey, f"{fid}_den")
            vals[f"{fid}_num"] = _str_or_none(num_v)
            vals[f"{fid}_den"] = _str_or_none(den_v)
            computed = calculations.compute_ratio_value(num_v, den_v, row["formula_type"])
            vals[fid] = None if computed is None else _str_or_none(computed)

        elif itype == "category_breakdown":
            cfg = meta.CATEGORY_BREAKDOWN[fid]
            total = 0.0
            selected_labels = []
            for cat in cfg["categories"]:
                cid = f"{fid}_cat_{meta.slugify(cat)}"
                v = _live_value(bkey, cid)
                vals[cid] = _str_or_none(v)
                fv = calculations._to_float(v)
                if fv is not None and fv > 0:
                    total += fv
                    selected_labels.append(cat)
            oc = _live_value(bkey, f"{fid}_cat_other_count")
            ot = _live_value(bkey, f"{fid}_cat_other_text")
            vals[f"{fid}_cat_other_count"] = _str_or_none(oc)
            vals[f"{fid}_cat_other_text"] = ot if ot else None
            ocv = calculations._to_float(oc)
            if ocv is not None and ocv > 0:
                total += ocv
                selected_labels.append(f"Other ({ot})" if ot else "Other")
            vals[fid] = "; ".join(selected_labels) if selected_labels else None
            vals[cfg["total_field"]] = _str_or_none(total)

        elif itype == "multiselect":
            v = _live_value(bkey, fid) or []
            vals[fid] = "; ".join(v) if v else None
            other_v = _live_value(bkey, f"{fid}_other_text")
            vals[f"{fid}_other_text"] = other_v if other_v else None

        else:  # numeric / yesno / text / textarea
            v = _live_value(bkey, fid)
            if itype == "numeric":
                vals[fid] = _str_or_none(v)
            else:
                vals[fid] = v if v not in (None, "") else None
    return vals
