#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import csv
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook

# ------------------------------------------------------------------ the published rules
def read_suffixes(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    column = next(c for c in rows[0] if c.strip().lower() == "suffix")
    return {r[column].strip().upper() for r in rows if r[column].strip()}

def read_markers(path: Path) -> dict[str, str]:
    doc = Document(path)
    published: dict[str, str] = {}
    for table in doc.tables:
        header = [c.text.strip().lower() for c in table.rows[0].cells]
        if header[:2] != ["meaning", "value"]:
            continue
        for row in table.rows[1:]:
            published[row.cells[0].text.strip().lower()] = row.cells[1].text.strip()
        break
    if not published:
        raise SystemExit("Data_Governance.docx publishes no Meaning/Value table")

    def find(*needles: str) -> str:
        for meaning, value in published.items():
            if all(n in meaning for n in needles):
                return value
        raise SystemExit(f"no published value whose meaning mentions {needles}")

    return {
        "blank": find("blank marker"),
        "none": find("no fields taken"),
        "not_applicable": find("not applicable"),
        "merged": find("status", "every value from the survivor"),
        "backfilled": find("status", "at least one value from elsewhere"),
        "held": find("status", "conflict"),
    }

def read_columns(path: Path) -> tuple[list[str], list[str]]:
    wb = load_workbook(path, data_only=True)
    def header(sheet: str) -> list[str]:
        row = next(wb[sheet].iter_rows(min_row=1, max_row=1, values_only=True))
        return [str(c).strip() for c in row if c is not None]
    return header("VendorMaster"), header("MergeLog")

# ------------------------------------------------------------------ normalisation
def norm_name(value, suffixes: set[str]) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())
    tokens = text.split()
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return " ".join(tokens)

def norm_code(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

def make_is_blank(marker: str):
    def is_blank(value) -> bool:
        text = "" if value is None else str(value).strip()
        return text == "" or text.upper() == marker.upper()
    return is_blank

# ------------------------------------------------------------------ clustering
class Union:
    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, key):
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def join(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

def clusters(records, suffixes, is_blank):
    ids = [r["VendorID"] for r in records]
    union = Union(ids)
    by_name: dict[tuple[str, str], list[str]] = {}
    by_tax: dict[str, list[str]] = {}
    for r in records:
        key = (norm_name(r["LegalName"], suffixes), norm_code(r["RemitToPostcode"]))
        by_name.setdefault(key, []).append(r["VendorID"])
        if not is_blank(r["TaxID"]):
            by_tax.setdefault(norm_code(r["TaxID"]), []).append(r["VendorID"])
    for group in list(by_name.values()) + list(by_tax.values()):
        for other in group[1:]:
            union.join(group[0], other)

    grouped: dict[str, list[str]] = {}
    for vid in ids:
        grouped.setdefault(union.find(vid), []).append(vid)
    return [sorted(members) for members in grouped.values() if len(members) > 1]

# ------------------------------------------------------------------ survivorship
def pick(candidates):
    latest = max(str(r["LastUpdated"] or "") for r in candidates)
    tied = [r for r in candidates if str(r["LastUpdated"] or "") == latest]
    return min(tied, key=lambda r: str(r["VendorID"]))

def solve(workspace: Path) -> tuple[int, int]:
    policy = workspace / "policy"
    suffixes = read_suffixes(policy / "legal_suffixes.csv")
    markers = read_markers(policy / "Data_Governance.docx")
    columns, log_columns = read_columns(workspace / "Format_Example.xlsx")
    is_blank = make_is_blank(markers["blank"])

    source = load_workbook(workspace / "vendor_master.xlsx", data_only=True)["VendorMaster"]
    rows = list(source.iter_rows(values_only=True))
    header = [str(c).strip() for c in rows[0]]
    records = [dict(zip(header, r)) for r in rows[1:]
               if r is not None and any(c is not None for c in r)]
    by_id = {r["VendorID"]: r for r in records}

    def clean(value):
        return "" if is_blank(value) else value

    merged_rows: list[dict] = []
    log_rows: list[dict] = []
    absorbed: set[str] = set()

    for members in clusters(records, suffixes, is_blank):
        cluster = [by_id[m] for m in members]
        survivor = pick(cluster)
        others = [r for r in cluster if r is not survivor]

        identifiers = {norm_code(r["TaxID"]) for r in cluster if not is_blank(r["TaxID"])}
        if len(identifiers) > 1:
            log_rows.append({
                log_columns[0]: survivor["VendorID"],
                log_columns[1]: ";".join(sorted(r["VendorID"] for r in others)),
                log_columns[2]: markers["not_applicable"],
                log_columns[3]: markers["held"],
            })
            continue

        taken: set[str] = set()
        row = {"VendorID": survivor["VendorID"]}
        for column in columns:
            if column in ("VendorID", "TaxID", "SpendYTD"):
                continue
            if not is_blank(survivor[column]):
                row[column] = survivor[column]
                continue
            donors = [r for r in others if not is_blank(r[column])]
            if donors:
                row[column] = pick(donors)[column]
                taken.add(column)
            else:
                row[column] = ""

        if not is_blank(survivor["TaxID"]):
            row["TaxID"] = survivor["TaxID"]
        else:
            donors = [r for r in others if not is_blank(r["TaxID"])]
            if donors:
                row["TaxID"] = pick(donors)["TaxID"]
                taken.add("TaxID")
            else:
                row["TaxID"] = ""

        total = sum((Decimal(str(r["SpendYTD"])) for r in cluster
                     if not is_blank(r["SpendYTD"])), Decimal(0))
        row["SpendYTD"] = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        merged_rows.append(row)
        absorbed.update(r["VendorID"] for r in others)
        ordered = [c for c in columns if c in taken]
        log_rows.append({
            log_columns[0]: survivor["VendorID"],
            log_columns[1]: ";".join(sorted(r["VendorID"] for r in others)),
            log_columns[2]: ";".join(ordered) if ordered else markers["none"],
            log_columns[3]: markers["backfilled"] if ordered else markers["merged"],
        })

    survivors = {r["VendorID"] for r in merged_rows}
    for record in records:
        if record["VendorID"] in absorbed or record["VendorID"] in survivors:
            continue
        merged_rows.append({c: clean(record[c]) for c in columns})

    merged_rows.sort(key=lambda r: str(r["VendorID"]))
    log_rows.sort(key=lambda r: str(r[log_columns[0]]))

    register = Workbook()
    sheet = register.active
    sheet.title = "VendorMaster"
    sheet.append(columns)
    for row in merged_rows:
        sheet.append([row.get(c, "") for c in columns])
    register.save(workspace / "vendor_master_merged.xlsx")

    book = Workbook()
    log = book.active
    log.title = "MergeLog"
    log.append(log_columns)
    for row in log_rows:
        log.append([row.get(c, "") for c in log_columns])
    book.save(workspace / "merge_log.xlsx")

    return len(merged_rows), len(log_rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    kept, logged = solve(ap.parse_args().workspace)
    print(f"consolidated register holds {kept} vendors; merge log holds {logged} clusters")
PY

echo "Done!"
