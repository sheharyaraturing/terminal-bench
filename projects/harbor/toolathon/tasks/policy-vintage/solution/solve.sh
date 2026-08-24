#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook

COVER = "Document: Group Expense Policy"

def as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    return date.fromisoformat(text) if text else None

def table_rows(doc: Document, needle: str) -> dict[str, Decimal]:
    for table in doc.tables:
        header = [cell.text.strip() for cell in table.rows[0].cells]
        if len(header) < 2 or needle.lower() not in header[1].lower():
            continue
        out: dict[str, Decimal] = {}
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) >= 2 and cells[0]:
                out[cells[0].strip().lower()] = Decimal(cells[1].replace(",", ""))
        return out
    return {}

def read_policy(path: Path) -> dict | None:
    doc = Document(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs]
    if not any(p == COVER for p in paragraphs):
        return None
    body = "\n".join(paragraphs)

    version = re.search(r"^Version:\s*(\S+)\s*$", body, re.M)
    status = re.search(r"^Status:\s*(\S+)\s*$", body, re.M)
    effective = re.search(r"^Effective date:\s*(\d{4}-\d{2}-\d{2})\s*$", body, re.M)
    threshold = re.search(
        r"settled amount of that line\s+is\s+([\d.,]+)\s+or more", body)
    if not (version and status and effective and threshold):
        return None

    return {
        "version": version.group(1),
        "status": status.group(1).upper(),
        "effective": date.fromisoformat(effective.group(1)),
        "receipt_threshold": Decimal(threshold.group(1).replace(",", "")),
        "ceilings": table_rows(doc, "subsistence"),
        "rates": table_rows(doc, "settlement rate"),
    }

def load_policies(ws: Path) -> list[dict]:
    found = []
    for path in sorted(ws.rglob("*.docx")):
        policy = read_policy(path)
        if policy:
            found.append(policy)
    return found

def governing(policies: list[dict], when: date) -> dict | None:
    live = [p for p in policies
            if p["status"] == "APPROVED" and p["effective"] <= when]
    return max(live, key=lambda p: p["effective"]) if live else None

def settled(amount: Decimal, currency: str, policy: dict) -> Decimal:
    rate = policy["rates"].get(currency.strip().lower(), Decimal("1"))
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def ceiling(destination: str, policy: dict) -> Decimal:
    table = policy["ceilings"]
    key = destination.strip().lower()
    if key in table:
        return table[key]
    for name, value in table.items():
        if "other" in name:
            return value
    raise SystemExit("no all-other-locations row in the subsistence appendix")

def output_header(ws: Path) -> list[str]:
    example = ws / "Format_Example.xlsx"
    if example.exists():
        for sheet in load_workbook(example, data_only=True).worksheets:
            row = next(sheet.iter_rows(values_only=True), None)
            if row and any(c and "version" in str(c).lower() for c in row):
                return [str(c).strip() for c in row if c is not None]
    return ["Claim", "Line", "VersionApplied", "Verdict", "Reason"]

def claim_sheet(path: Path):
    book = load_workbook(path, data_only=True)
    for sheet in book.worksheets:
        row = next(sheet.iter_rows(values_only=True), None)
        if row and "Claim" in [str(c).strip() for c in row if c is not None]:
            return sheet
    return book.worksheets[0]

def solve(ws: Path) -> int:
    policies = load_policies(ws)
    if not policies:
        raise SystemExit("no expense policy documents found in the workspace")

    sheet = claim_sheet(ws / "claims.xlsx")
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c).strip() for c in rows[0]]
    records = [dict(zip(header, r)) for r in rows[1:]
               if r and any(c is not None for c in r)]

    decisions = []
    for rec in records:
        when = as_date(rec.get("ExpenseDate"))
        if when is None:
            decisions.append((rec["Claim"], rec["Line"],
                              "UNDETERMINED", "HOLD", "NO_EXPENSE_DATE"))
            continue

        policy = governing(policies, when)
        if policy is None:
            raise SystemExit(f"no approved policy in force on {when}")

        amount = settled(Decimal(str(rec["Amount"])), str(rec["Currency"]), policy)
        receipt = str(rec.get("Receipt") or "").strip().lower() == "yes"

        if amount >= policy["receipt_threshold"] and not receipt:
            verdict, reason = "REJECT", "NO_RECEIPT"
        elif amount <= ceiling(str(rec["Destination"]), policy):
            verdict, reason = "APPROVE", "WITHIN_CAP"
        else:
            verdict, reason = "REJECT", "OVER_CAP"

        decisions.append((rec["Claim"], rec["Line"], policy["version"], verdict, reason))

    book = Workbook()
    out = book.active
    out.title = "Decisions"
    out.append(output_header(ws))
    for row in decisions:
        out.append(list(row))
    book.save(ws / "decisions.xlsx")
    return len(decisions)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    print(f"decided {solve(ap.parse_args().workspace)} claim lines")
PY

echo "Done!"
