"""
calculations.py
Pure functions ported verbatim from global.R's compute_ratio_value /
format_ratio_display / compute_naat_capacity, plus the category-breakdown
total helper implied by server.R's live `_calc` outputs. Keep these in exact
numeric/formatting parity with the R app - this is the module a regression
test should target.
"""
from __future__ import annotations

from meta import NAAT_CAPACITY_CONFIG


def _to_float(v):
    """Best-effort numeric coercion; returns None on blank/invalid, mirroring
    R's suppressWarnings(as.numeric(...)) -> NA behaviour."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def compute_ratio_value(num, den, formula_type: str):
    """Returns the computed float, or None if inputs are missing/den==0."""
    num_v = _to_float(num)
    den_v = _to_float(den)
    if num_v is None or den_v is None or den_v == 0:
        return None
    if formula_type == "PCT":
        return num_v / den_v * 100
    if formula_type == "LAKH":
        return num_v / den_v * 1e5
    if formula_type == "RATIO":
        return num_v / den_v
    return None


def format_ratio_display(val, formula_type: str) -> str:
    if val is None:
        return "Enter numerator & denominator above"
    if formula_type == "PCT":
        return f"{_round2(val)} %"
    if formula_type == "LAKH":
        return f"{_comma(_round2(val))} per 1,00,000 population"
    if formula_type == "RATIO":
        return f"{_round2(val)} : 1"
    return str(_round2(val))


def _round2(val: float) -> str:
    r = round(val, 2)
    # Match R's round() display: drop a trailing .0 the way as.character(round(x,2)) would not,
    # but keep it simple/consistent - show up to 2 decimals, no trailing zeros beyond that.
    if r == int(r):
        return str(int(r))
    return f"{r:.2f}".rstrip("0").rstrip(".")


def _comma(s: str) -> str:
    """Thousands-comma format matching scales::comma() for a numeric string."""
    if "." in s:
        whole, frac = s.split(".", 1)
        neg = whole.startswith("-")
        if neg:
            whole = whole[1:]
        whole = f"{int(whole):,}"
        return f"{'-' if neg else ''}{whole}.{frac}"
    neg = s.startswith("-")
    core = s[1:] if neg else s
    return f"{'-' if neg else ''}{int(core):,}"


def compute_category_total(values: list) -> int:
    """Sum of per-category counts + Other count, treating blank/None as 0."""
    total = 0
    for v in values:
        fv = _to_float(v)
        if fv is not None:
            total += fv
    return int(total) if total == int(total) else total


def compute_naat_capacity(module_counts, shifts, cfg=None):
    cfg = cfg or NAAT_CAPACITY_CONFIG
    modules = 0.0
    for v in module_counts:
        fv = _to_float(v)
        if fv is not None:
            modules += fv
    shifts_v = _to_float(shifts)
    if shifts_v is None or shifts_v <= 0:
        return None
    return (
        modules
        * cfg["tests_per_module_per_shift_per_day"]
        * shifts_v
        * cfg["working_days_per_month"]
        * cfg["months_per_year"]
    )
