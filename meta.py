"""
meta.py
Loaded once at import time. Reads data/field_metadata.csv (auto-extracted from
Block Template.xlsx, one row per data column, in original column order) and
derives every structure the rest of the app needs: sections, ratio fields,
backend-only fields, category-breakdown config, multiselect option lists, and
the full list of DB columns the `entries` table must have.

This is a direct port of the "Field metadata" and related sections of the
original R Shiny app's global.R - see that file for the reference behaviour.
Do not hand-edit field_metadata.csv; regenerate it if the source template
changes.
"""
import os
import re
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIELD_META_CSV = os.path.join(DATA_DIR, "field_metadata.csv")
MASTER_LOCATIONS_SEED_CSV = os.path.join(DATA_DIR, "master_locations_seed.csv")

# ---------------------------------------------------------------------------
# Field metadata
# ---------------------------------------------------------------------------
_raw = pd.read_csv(FIELD_META_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
_raw["idx"] = _raw["idx"].astype(float)
_raw.loc[_raw["idx"].isin([2.0, 3.0, 4.0]), "section"] = "Location"
field_meta = _raw.sort_values("idx").reset_index(drop=True)

LOC_FIELDS = field_meta.loc[field_meta.input_type == "location", "field_id"].tolist()
FORM_FIELDS = field_meta.loc[field_meta.input_type != "location"].reset_index(drop=True)

RATIO_FIELDS = FORM_FIELDS.loc[FORM_FIELDS.input_type == "ratio"].reset_index(drop=True)
BACKEND_FIELD_IDS = set(FORM_FIELDS.loc[FORM_FIELDS.is_backend == "TRUE", "field_id"].tolist())

RATIO_EXTRA_COLS = []
for _fid in RATIO_FIELDS.field_id:
    RATIO_EXTRA_COLS.append(f"{_fid}_num")
    RATIO_EXTRA_COLS.append(f"{_fid}_den")

# Preserve first-seen order, de-duplicated (matches R's unique(FORM_FIELDS$section))
SECTIONS = list(dict.fromkeys(FORM_FIELDS.section.tolist()))


def sec_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).lower()


# ---------------------------------------------------------------------------
# Multi-select curated option lists (matches multiselect_lookup in global.R)
# ---------------------------------------------------------------------------
MULTISELECT_LOOKUP = {
    "congregate": ["Urban slum", "Workplace", "Prison", "Orphanage", "Other"],
    "vulnerable population": [
        "Diabetics", "Alcoholics", "Elderly", "Smokers", "PLHIV",
        "Past H/O TB", "Contact of previous TB", "Other",
    ],
    "adherence technolog": [
        "99DOTS", "Video Observed Treatment (VOT)",
        "Medication Event Reminder Monitor", "Manual", "Other",
    ],
    "earmarked beds": ["PHC", "CHC", "SDH/Taluk Hospital", "DH", "Medical College", "Other"],
    "assesment done": ["Baseline", "FU 1st month", "FU 2nd month", "FU 3rd month", "Other"],
}


def get_multiselect_choices(field_name: str):
    nm = field_name.lower()
    for key, choices in MULTISELECT_LOOKUP.items():
        if key in nm:
            return choices
    return ["Other"]


MULTISELECT_OTHER_COLS = [
    f"{fid}_other_text" for fid in FORM_FIELDS.loc[FORM_FIELDS.input_type == "multiselect", "field_id"]
]

# ---------------------------------------------------------------------------
# Category-breakdown fields ("Type of X" -> paired read-only Total)
# ---------------------------------------------------------------------------
CATEGORY_BREAKDOWN = {
    "f024": {  # Type of congregate settings -> Total population of congregate settings
        "total_field": "f025",
        "categories": ["Urban slum", "Workplace", "Prison", "Orphanage"],
    },
    "f026": {  # Type of Vulnerable Population -> Total Vulnerable population
        "total_field": "f027",
        "categories": [
            "Diabetics", "Alcoholics", "Elderly", "Smokers", "PLHIV",
            "Past H/O TB", "Contact of previous TB",
        ],
    },
}


def category_field_ids(fid: str):
    cats = CATEGORY_BREAKDOWN[fid]["categories"]
    ids = [f"{fid}_cat_{slugify(c)}" for c in cats]
    ids.append(f"{fid}_cat_other_count")
    ids.append(f"{fid}_cat_other_text")
    return ids


CATEGORY_EXTRA_COLS = []
for _fid in CATEGORY_BREAKDOWN:
    CATEGORY_EXTRA_COLS.extend(category_field_ids(_fid))

TOTAL_TO_BREAKDOWN = {cfg["total_field"]: fid for fid, cfg in CATEGORY_BREAKDOWN.items()}

# ---------------------------------------------------------------------------
# NAAT testing capacity config (matches NAAT_CAPACITY_CONFIG in global.R)
# ---------------------------------------------------------------------------
NAAT_CAPACITY_CONFIG = dict(
    total_field="f071",
    shifts_field="f071a",
    modules_ref_field="f071b",
    module_fields=["f062", "f064"],
    tests_per_module_per_shift_per_day=6,
    working_days_per_month=20,
    months_per_year=12,
)

# ---------------------------------------------------------------------------
# Full set of columns the `entries` table needs (excluding state/district/block
# PK and status/submitted_by/updated_at, added separately by db.py)
# ---------------------------------------------------------------------------
ALL_ENTRY_FIELD_COLS = (
    FORM_FIELDS["field_id"].tolist() + RATIO_EXTRA_COLS + CATEGORY_EXTRA_COLS + MULTISELECT_OTHER_COLS
)


def backend_csv_column_name(row, part=None):
    """Human-readable CSV column name for a backend field - used for both the
    downloadable template and matching columns back on upload."""
    if part is None:
        return row["field_name"]
    if part == "num":
        return f"{row['field_name']} - NUMERATOR ({row['note']})"
    if part == "den":
        return f"{row['field_name']} - DENOMINATOR ({row['denominator']})"
    raise ValueError(part)


BACKEND_FIELDS = FORM_FIELDS.loc[FORM_FIELDS.is_backend == "TRUE"].reset_index(drop=True)
