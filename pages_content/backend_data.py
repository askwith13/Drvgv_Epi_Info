"""
pages_content/backend_data.py
Port of ui.R's "backend_data" tabItem / server.R's backend push logic
(master admin only). Note: exactly like the R app, every non-ratio backend
field is rendered as a plain numeric box regardless of its nominal
input_type in field_metadata.csv (e.g. f162 is "textarea" in the metadata
but the R app's backend_fields_ui always uses numericInput for non-ratio
backend fields) - replicated here for parity.
"""
import pandas as pd
import streamlit as st

import auth
import calculations
import db
import meta
import scope


def render():
    user = auth.current_user()
    master = db.get_master_locations()

    with st.container(border=True):
        st.markdown('<div class="box-title">Push backend data for a single block</div>', unsafe_allow_html=True)
        st.write(
            "These 5 indicators can't be filled in by field staff — they come from Nikshay analytics or the "
            "TBMB mobile app backend. Use this form to enter them for one block at a time, or use the bulk "
            "CSV upload below for many blocks at once. Nothing else in the block's record is affected."
        )
        if master.empty:
            st.warning("No master location list configured yet.")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            states = sorted(master.state.dropna().unique().tolist())
            state = scope.safe_selectbox("State", states, "bk_sel_state")
        with c2:
            districts = sorted(master.loc[master.state == state, "district"].dropna().unique().tolist()) if state else []
            district = scope.safe_selectbox("District", districts, "bk_sel_district")
        with c3:
            blocks = (
                sorted(master.loc[(master.state == state) & (master.district == district), "block"].dropna().unique().tolist())
                if state and district else []
            )
            block = scope.safe_selectbox("Block", blocks, "bk_sel_block")

        if not (state and district and block):
            return

        rec = db.load_entry(state, district, block) or {}
        entries_widgets = {}
        cols = st.columns(2)
        for i, (_, row) in enumerate(meta.BACKEND_FIELDS.iterrows()):
            fid = row["field_id"]
            with cols[i % 2]:
                with st.container(border=True):
                    if row["input_type"] == "ratio":
                        st.markdown(f"**{row['field_name']}**")
                        num_v = calculations._to_float(rec.get(f"{fid}_num"))
                        den_v = calculations._to_float(rec.get(f"{fid}_den"))
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            num = st.number_input(f"Numerator: {row['note'] or ''}", value=num_v,
                                                   key=f"bk_{fid}_num", step=1.0)
                        with cc2:
                            den = st.number_input(f"Denominator: {row['denominator'] or ''}", value=den_v,
                                                   key=f"bk_{fid}_den", step=1.0)
                        val = calculations.compute_ratio_value(num, den, row["formula_type"])
                        st.markdown(
                            f'<span class="calc-value">{calculations.format_ratio_display(val, row["formula_type"])}</span>',
                            unsafe_allow_html=True,
                        )
                        entries_widgets[fid] = ("ratio", num, den, row)
                    else:
                        v = calculations._to_float(rec.get(fid))
                        val = st.number_input(row["field_name"], value=v, key=f"bk_{fid}", step=1.0)
                        entries_widgets[fid] = ("plain", val, None, row)

        st.markdown('<div class="btn-success-wrap">', unsafe_allow_html=True)
        if st.button("💾 Save Backend Data", key="btn_save_backend"):
            payload = {}
            for fid, (kind, a, b, row) in entries_widgets.items():
                if kind == "ratio":
                    payload[f"{fid}_num"] = _str_or_none(a)
                    payload[f"{fid}_den"] = _str_or_none(b)
                    comp = calculations.compute_ratio_value(a, b, row["formula_type"])
                    payload[fid] = _str_or_none(comp) if comp is not None else None
                else:
                    payload[fid] = _str_or_none(a)
            try:
                db.save_backend_values(state, district, block, payload, user["username"])
                st.success(f"Backend data saved for {block}, {district}, {state}.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Save failed. Details: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="box-title">Bulk upload via CSV</div>', unsafe_allow_html=True)
        st.write(
            "For periodic Nikshay/TBMB data dumps covering many blocks at once. Download the template below "
            "— it includes one example row showing the expected format, which you should delete before "
            "adding your real rows (one row per block) and uploading."
        )
        st.download_button("⬇️ Download CSV Template", _build_template_csv(),
                           file_name="backend_data_template.csv", mime="text/csv")
        st.write("**Column reference:**")
        st.dataframe(_column_legend(), width="stretch", hide_index=True)
        upload = st.file_uploader("Upload filled-in CSV", type="csv", key="backend_csv_upload")
        st.markdown('<div class="btn-danger-wrap">', unsafe_allow_html=True)
        if st.button("⬆️ Upload Backend Data", key="btn_upload_backend"):
            if upload is None:
                st.error("Choose a CSV file first.")
            else:
                _handle_bulk_upload(upload, user["username"])
        st.markdown("</div>", unsafe_allow_html=True)


def _str_or_none(v):
    fv = calculations._to_float(v)
    if fv is None:
        return None
    return str(int(fv)) if fv == int(fv) else str(fv)


def _column_legend():
    rows = []
    for _, row in meta.BACKEND_FIELDS.iterrows():
        if row["input_type"] == "ratio":
            cols = f"{meta.backend_csv_column_name(row, 'num')}   AND   {meta.backend_csv_column_name(row, 'den')}"
        else:
            cols = meta.backend_csv_column_name(row)
        rows.append({"CSV column(s) to fill in": cols})
    return pd.DataFrame(rows)


def _build_template_csv():
    example_vals = {"f067": "1500", "f072_num": "120", "f072_den": "300",
                     "f162": "45", "f177": "80", "f178": "65"}
    cols = ["State", "District", "Block"]
    example_row = ["SAMPLE STATE 1 (delete this row)", "SAMPLE DISTRICT 1A", "Block 1"]
    for _, row in meta.BACKEND_FIELDS.iterrows():
        fid = row["field_id"]
        if row["input_type"] == "ratio":
            cols += [meta.backend_csv_column_name(row, "num"), meta.backend_csv_column_name(row, "den")]
            example_row += [example_vals.get(f"{fid}_num", ""), example_vals.get(f"{fid}_den", "")]
        else:
            cols.append(meta.backend_csv_column_name(row))
            example_row.append(example_vals.get(fid, ""))
    df = pd.DataFrame([example_row], columns=cols)
    return df.to_csv(index=False).encode("utf-8")


def _handle_bulk_upload(upload, pushed_by):
    try:
        df = pd.read_csv(upload, dtype=str, keep_default_na=False)
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read CSV. Details: {e}")
        return
    if not {"State", "District", "Block"}.issubset(df.columns):
        st.error("CSV must have columns: State, District, Block (plus the backend field columns — use the "
                 "downloaded template).")
        return
    n_ok, n_skip = 0, 0
    for i, r in df.iterrows():
        st_ = str(r.get("State", "")).strip()
        di_ = str(r.get("District", "")).strip()
        bl_ = str(r.get("Block", "")).strip()
        if not st_ or not di_ or not bl_:
            n_skip += 1
            continue
        payload = {}
        for _, row in meta.BACKEND_FIELDS.iterrows():
            fid = row["field_id"]
            if row["input_type"] == "ratio":
                ncol = meta.backend_csv_column_name(row, "num")
                dcol = meta.backend_csv_column_name(row, "den")
                nv = calculations._to_float(r.get(ncol)) if ncol in df.columns else None
                dv = calculations._to_float(r.get(dcol)) if dcol in df.columns else None
                if ncol in df.columns:
                    payload[f"{fid}_num"] = _str_or_none(nv)
                if dcol in df.columns:
                    payload[f"{fid}_den"] = _str_or_none(dv)
                comp = calculations.compute_ratio_value(nv, dv, row["formula_type"])
                payload[fid] = _str_or_none(comp) if comp is not None else None
            else:
                col = meta.backend_csv_column_name(row)
                if col in df.columns:
                    v = r.get(col)
                    payload[fid] = str(v).strip() if v not in (None, "") else None
        try:
            db.save_backend_values(st_, di_, bl_, payload, pushed_by)
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            st.error(f"Upload stopped after {n_ok} block(s) saved. Details: {e}")
            return
    msg = f"Backend data uploaded for {n_ok} block(s)."
    if n_skip:
        msg += f" {n_skip} row(s) skipped (missing State/District/Block)."
    st.success(msg)
