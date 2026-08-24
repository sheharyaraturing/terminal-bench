#!/usr/bin/env bash

set -euo pipefail

export PATH="/root/.local/bin:${PATH}"

WORKSPACE="${PWD}"

cd /workspace

cat > /tmp/solve.py <<'PY'
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook, load_workbook

NA = "N/A"
MISSING_STRINGS = {"", "N/A", "—"}


def d(value):
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if s in MISSING_STRINGS:
            return None
        s = s.replace(",", "")
    else:
        s = str(value)
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Unexpected revenue value: {value!r}")


def read_master(ws: Path):
    rows = []
    with (ws / "segment_master.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({**r, "DisplayOrder": int(r["DisplayOrder"])})
    rows.sort(key=lambda x: x["DisplayOrder"])
    return rows


def read_raw(ws: Path):
    book = load_workbook(ws / "segments.xlsx", data_only=True)
    sh = book["RawData"]
    headers = [c.value for c in sh[1]]
    year_cols = {int(v): i + 1 for i, v in enumerate(headers) if isinstance(v, int)}
    out = {}
    for row in sh.iter_rows(min_row=2, values_only=True):
        sid = row[0]
        if not sid:
            continue
        vals = {}
        for yr, col1 in year_cols.items():
            vals[yr] = d(row[col1 - 1])
        out[str(sid).strip()] = vals
    return out


def read_methodology(ws: Path):
    sh = load_workbook(ws / "segments.xlsx", data_only=True)["Methodology"]
    values = [[c.value for c in row] for row in sh.iter_rows()]

    def section_row(title):
        for i, row in enumerate(values):
            if row and row[0] == title:
                return i
        raise ValueError(f"Missing methodology section: {title}")

    # Class rules
    i = section_row("Class rules") + 2
    class_rules = {}
    while i < len(values) and values[i][0]:
        class_rules[str(values[i][0]).strip()] = str(values[i][1]).strip()
        i += 1

    # Overrides
    i = section_row("Segment-year overrides") + 2
    overrides = {}
    while i < len(values) and values[i][0]:
        overrides[(str(values[i][0]).strip(), int(values[i][1]))] = str(values[i][2]).strip()
        i += 1

    # Rounding settings
    i = section_row("Rounding & representation") + 2
    settings = {}
    while i < len(values) and values[i][0]:
        settings[str(values[i][0]).strip()] = str(values[i][1]).strip()
        i += 1
    if settings.get("Rounding mode") != "ROUND_HALF_UP" or settings.get("Precision") != "1 decimal place":
        raise ValueError("Oracle only supports the active FY26-P1 rounding contract")

    return class_rules, overrides


def apply_restatements(ws: Path, revenue, as_of: date):
    candidates = {}
    with (ws / "restatements.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Status"].strip() != "Approved":
                continue
            published = date.fromisoformat(r["PublishedAt"].strip())
            if published > as_of:
                continue
            key = (r["SegmentID"].strip(), int(r["Year"]))
            if key not in candidates or published > candidates[key][0]:
                candidates[key] = (published, d(r["Revenue"]))
    for (sid, yr), (_, val) in candidates.items():
        revenue.setdefault(sid, {})[yr] = val


def calc(prev, cur, rule):
    if prev is None or cur is None or prev == 0:
        return NA
    if rule == "STANDARD_NO_SIGN_CHANGE" and ((prev < 0 < cur) or (cur < 0 < prev)):
        return NA
    if rule in ("STANDARD", "STANDARD_NO_SIGN_CHANGE"):
        denom = prev
    elif rule == "ABS_DENOMINATOR":
        denom = abs(prev)
    else:
        raise ValueError(f"Unknown rule {rule}")
    value = (cur - prev) / denom * Decimal(100)
    value = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if value == 0:
        value = Decimal("0.0")
    return float(value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args()
    ws = Path(args.workspace)

    cfg = json.loads((ws / "planning_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((ws / "source_manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "ACTIVE" or manifest["policy_version"] != cfg["policy_version"]:
        raise ValueError("Active manifest/config policy mismatch")

    as_of = date.fromisoformat(cfg["as_of_date"])
    growth_years = [int(x) for x in cfg["growth_years"]]
    master = read_master(ws)
    revenue = read_raw(ws)
    class_rules, overrides = read_methodology(ws)
    apply_restatements(ws, revenue, as_of)

    out = Workbook()
    sh = out.active
    sh.title = cfg["output_sheet"]
    sh.append(["Segment"] + growth_years)

    for rec in master:
        sid, name, cls = rec["SegmentID"], rec["Segment"], rec["Class"]
        vals = revenue.get(sid, {})
        row = [name]
        for yr in growth_years:
            rule = overrides.get((sid, yr), class_rules[cls])
            row.append(calc(vals.get(yr - 1), vals.get(yr), rule))
        sh.append(row)
    out.save(ws / cfg["output_file"])


if __name__ == "__main__":
    main()

PY

uv run python /tmp/solve.py --workspace "${WORKSPACE}"
echo "Done!"