#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook

LONG_DATE = re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\b")

def parse_long_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%d %B %Y").date()

# ---------------------------------------------------------------- the manual
class Manual:
    def __init__(self, path: Path) -> None:
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)

        m = re.search(r"run date for the current cycle is\s+" + LONG_DATE.pattern, text)
        if not m:
            raise SystemExit("AP_Manual.docx: no run date")
        self.run_date = parse_long_date(m.group(1))

        m = re.search(r"whose Status is exactly\s+(\w+)", text)
        self.status = m.group(1) if m else "Open"

        m = re.search(
            r"payment period is\s+(\d+)\s+calendar days and the governing source is\s+"
            r"([A-Z][A-Z0-9\-]*\s+clause\s+[\d.]+)",
            text,
        )
        if not m:
            raise SystemExit("AP_Manual.docx: no default payment period")
        self.default_days = int(m.group(1))
        self.default_source = re.sub(r"\s+", " ", m.group(2)).rstrip(".")

        m = re.search(
            r"Record DueDate as\s+([A-Z][A-Z\-]*)\s+and GoverningSource as\s+([A-Z][A-Z\-]*)",
            text,
        )
        if not m:
            raise SystemExit("AP_Manual.docx: no unresolved-record sentinel")
        self.flag_due, self.flag_source = m.group(1), m.group(2)

        self.entity_of: dict[str, str] = {}
        for table in doc.tables:
            head = [c.text.strip().lower() for c in table.rows[0].cells]
            if len(head) < 2 or "trading" not in head[0]:
                continue
            for row in table.rows[1:]:
                trading, legal = (c.text.strip() for c in row.cells[:2])
                if trading and legal:
                    self.entity_of[trading] = legal
        if not self.entity_of:
            raise SystemExit("AP_Manual.docx: no supplier register")

# ---------------------------------------------------------------- the documents
class SupplierDoc:
    def __init__(self, path: Path) -> None:
        doc = Document(path)
        self.paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        self.fields: dict[str, str] = {}
        for line in self.paragraphs[:14]:
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                if key and key not in self.fields:
                    self.fields[key] = value.strip()

        self.ref = self.fields.get("document reference", path.stem)
        self.kind = self.fields.get("document type", "").lower()
        self.entity = self.fields.get("supplier", "")
        self.amends = self.fields.get("amends contract", "")

        self.start = self._date("commencement date") or self._date("effective date")
        self.end = self._date("expiry date")
        self.effective = self._date("effective date")

        self.days: int | None = None
        self.clause: str | None = None
        for line in self.paragraphs:
            hit = re.search(
                r"shall pay each correctly rendered[^.]*?within\s+[a-z\- ]*\((\d+)\)\s+days "
                r"of the date of the invoice",
                line,
                re.IGNORECASE,
            )
            if not hit:
                continue
            self.days = int(hit.group(1))
            lead = re.match(r"^(\d+(?:\.\d+)*)[.\s]", line)
            self.clause = lead.group(1) if lead else ""
            break

    def _date(self, key: str) -> date | None:
        value = self.fields.get(key)
        if not value:
            return None
        m = LONG_DATE.search(value)
        return parse_long_date(m.group(1)) if m else None

    @property
    def is_amendment(self) -> bool:
        return "amendment" in self.kind and self.days is not None

    @property
    def is_contract(self) -> bool:
        return (
            "supply agreement" in self.kind
            and "amendment" not in self.kind
            and self.days is not None
            and self.start is not None
            and self.end is not None
        )

    def source(self) -> str:
        return f"{self.ref} clause {self.clause}"

# ---------------------------------------------------------------- the rules
def roll(day: date) -> date:
    if day.weekday() == 5:
        return day + timedelta(days=2)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day

def governing(entity: str, when: date, contracts, amendments):
    live = [c for c in contracts if c.entity == entity and c.start <= when <= c.end]
    if not live:
        return None, None

    options: list[tuple[int, str]] = []
    for contract in live:
        applicable = [
            a for a in amendments
            if a.amends == contract.ref and a.effective is not None and a.effective <= when
        ]
        if applicable:
            latest = max(applicable, key=lambda a: a.effective)
            options.append((latest.days, latest.source()))
        else:
            options.append((contract.days, contract.source()))

    if len({days for days, _ in options}) > 1:
        return "FLAG", None
    return sorted(options, key=lambda o: o[1])[0]

def solve(workspace: Path) -> int:
    manual = Manual(workspace / "manual" / "AP_Manual.docx")

    docs = [SupplierDoc(p) for p in sorted((workspace / "contracts").glob("*.docx"))]
    contracts = [d for d in docs if d.is_contract]
    amendments = [d for d in docs if d.is_amendment]

    sheet = load_workbook(workspace / "open_invoices.xlsx", data_only=True).active
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c).strip() for c in rows[0]]
    records = [dict(zip(header, r)) for r in rows[1:] if r and any(c is not None for c in r)]

    def as_date(value) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    example = load_workbook(workspace / "manual" / "Format_Example.xlsx")
    shape = example[example.sheetnames[0]]
    columns = [str(c).strip() for c in next(shape.iter_rows(values_only=True))]

    out = Workbook()
    schedule = out.active
    schedule.title = shape.title
    schedule.append(columns)

    scheduled = 0
    for record in sorted(records, key=lambda r: str(r["Invoice"])):
        if str(record["Status"]).strip() != manual.status:
            continue
        raised = as_date(record["InvoiceDate"])
        if raised > manual.run_date:
            continue

        vendor = str(record["Vendor"]).strip()
        entity = manual.entity_of.get(vendor, "")
        days, source = governing(entity, raised, contracts, amendments)

        if days == "FLAG":
            due, source = manual.flag_due, manual.flag_source
        else:
            if days is None:
                days, source = manual.default_days, manual.default_source
            due = roll(raised + timedelta(days=days)).isoformat()

        schedule.append([record["Invoice"], vendor, due, source])
        scheduled += 1

    out.save(workspace / "payment_schedule.xlsx")
    return scheduled

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    a = ap.parse_args()
    print(f"scheduled {solve(a.workspace)} invoices")
PY

echo "Done!"
