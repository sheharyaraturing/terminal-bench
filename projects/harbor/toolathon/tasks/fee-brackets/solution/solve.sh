#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import csv
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from docx import Document
from openpyxl import Workbook

CENTS = Decimal("0.01")

def money(text: str) -> int:
    return int((Decimal(text.replace(",", "").strip()) * 100).to_integral_value())

def read_schedule(path: Path) -> dict:
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs]
    blob = "\n".join(paras)

    spec: dict = {}

    m = re.search(r"Version\s+(FS-\d{4}-[A-Z])", blob)
    spec["version"] = m.group(1)

    m = re.search(r"balance snapshot dated\s+(\d{4}-\d{2}-\d{2})", blob)
    spec["snapshot_date"] = m.group(1)

    m = re.search(r"minimum chargeable balance is\s+([\d,]+\.\d\d)", blob)
    spec["minimum_cents"] = money(m.group(1))

    m = re.search(r"workbook named\s+(\S+\.xlsx)", blob)
    spec["workbook"] = m.group(1)

    m = re.search(r"worksheet named\s+([A-Za-z0-9_]+)", blob)
    spec["sheet"] = m.group(1)

    m = re.search(r"produces\s+(\S+\.json)\s", blob)
    spec["workings"] = m.group(1)

    m = re.search(r"the bare word\s+([A-Z_]+)", blob)
    spec["sentinel"] = m.group(1)

    m = re.search(r"^(Account\s*\|.+)$", blob, re.MULTILINE)
    spec["columns"] = [c.strip() for c in m.group(1).split("|")]

    spec["reasons"] = {}
    for line in paras:
        m = re.match(r"^([A-Z][A-Z_]+)\s+[—-]\s+the (.+)$", line)
        if m:
            spec["reasons"][m.group(1)] = m.group(2)

    bands: list[tuple[str, int, int | None, Decimal]] = []
    for table in doc.tables:
        head = [c.text.strip().lower() for c in table.rows[0].cells]
        if head[:4] != ["band", "portion over", "portion up to", "rate"]:
            continue
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            upper = None if not re.match(r"^[\d,.]+$", cells[2]) else money(cells[2])
            bands.append((cells[0], money(cells[1]), upper, Decimal(cells[3])))
        break
    spec["bands"] = bands
    return spec

def fee_for(cents: int, spec: dict) -> tuple[int, dict[str, int], int]:
    portions = {band: 0 for band, *_ in spec["bands"]}
    if cents < spec["minimum_cents"]:
        return 0, portions, 0
    exact = Decimal(0)
    for band, lo, hi, rate in spec["bands"]:
        top = cents if hi is None else min(cents, hi)
        portion = max(0, top - lo)
        portions[band] = portion
        exact += Decimal(portion) * rate
    fee = int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return fee, portions, cents - sum(portions.values())

def solve(workspace: Path) -> None:
    spec = read_schedule(workspace / "policy" / "Fee_Schedule.docx")
    sentinel = spec["sentinel"]

    with (workspace / "accounts.csv").open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if any(v.strip() for v in r.values())]

    closed = [r for r in rows if r["Status"].strip().upper() == "CLOSED"]
    survived_status = [r for r in rows if r["Status"].strip().upper() != "CLOSED"]
    house = [r for r in survived_status if r["AccountType"].strip().upper() == "HOUSE"]
    included = [r for r in survived_status if r["AccountType"].strip().upper() != "HOUSE"]

    grouped: dict[str, list[dict]] = {}
    for r in included:
        grouped.setdefault(r["Account"].strip(), []).append(r)
    collapsed = sum(len(v) - 1 for v in grouped.values())

    totals = {band: 0 for band, *_ in spec["bands"]}
    totals["unbanded"] = 0
    undefined: dict[str, str] = {}
    records: list[list] = []
    total_fee = 0

    for account in sorted(grouped):
        written = {r["Balance"].strip() for r in grouped[account]}
        reason = None
        cents = None
        if len(written) > 1:
            reason = "CONFLICTING_BALANCE"
        else:
            text = written.pop()
            if text == "":
                reason = "MISSING_BALANCE"
            else:
                try:
                    cents = int((Decimal(text) * 100).to_integral_value())
                except Exception:
                    reason = "UNREADABLE_BALANCE"

        if reason is not None:
            assert reason in spec["reasons"], reason
            undefined[account] = reason
            records.append([account, sentinel, sentinel, sentinel])
            continue

        fee, portions, unbanded = fee_for(cents, spec)
        for band, portion in portions.items():
            totals[band] += portion
        totals["unbanded"] += unbanded
        total_fee += fee
        rate = (Decimal(0) if fee == 0
                else (Decimal(fee) / Decimal(cents)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP))
        records.append([account, cents, fee, float(rate)])

    book = Workbook()
    sheet = book.active
    sheet.title = spec["sheet"]
    sheet.append(spec["columns"])
    for record in records:
        sheet.append(record)
    book.save(workspace / spec["workbook"])

    workings = {
        "metric": "progressive_fee_run",
        "schedule_version": spec["version"],
        "snapshot_date": spec["snapshot_date"],
        "accounts_in_file": len(rows),
        "accounts_reported": len(records),
        "total_fee_cents": total_fee,
        "excluded": {
            "closed": len(closed),
            "house": len(house),
            "duplicate_rows_collapsed": collapsed,
        },
        "undefined": dict(sorted(undefined.items())),
        "band_balance_cents": totals,
    }
    (workspace / spec["workings"]).write_text(
        json.dumps(workings, indent=2) + "\n", encoding="utf-8"
    )
    print(f"reported {len(records)} accounts, total_fee_cents={total_fee}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
