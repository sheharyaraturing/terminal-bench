#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import csv
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook


# ------------------------------------------------------------------ the procedure
def read_procedure(path: Path) -> dict:
    doc = Document(path)
    parameters: dict[str, str] = {}
    holidays: set[date] = set()
    channels: dict[str, str] = {}
    statuses: dict[str, str] = {}

    for table in doc.tables:
        header = [cell.text.strip().lower() for cell in table.rows[0].cells]
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows[1:]]
        if header[:2] == ["parameter", "value"]:
            parameters.update({r[0].strip().lower(): r[1].strip() for r in rows})
        elif header[:2] == ["date", "holiday"]:
            holidays.update(date.fromisoformat(r[0]) for r in rows)
        elif header[:2] == ["channel", "treatment"]:
            channels.update({r[0].upper(): r[1].strip().lower() for r in rows})
        elif header[:2] == ["status", "treatment"]:
            statuses.update({r[0].upper(): r[1].strip().lower() for r in rows})

    return {
        "window_start": date.fromisoformat(parameters["reconciliation window start"]),
        "window_end": date.fromisoformat(parameters["reconciliation window end"]),
        "amount_tolerance": Decimal(parameters["amount tolerance (gbp)"]),
        "date_tolerance": int(parameters["date tolerance (business days)"]),
        "places": int(parameters["monetary decimal places"]),
        "sentinel": parameters["undefined sentinel"],
        "output": parameters["output workbook"],
        "holidays": holidays,
        "channels_in": {c for c, t in channels.items() if t.startswith("in")},
        "statuses_in": {s for s, t in statuses.items() if t.startswith("in")},
    }


def read_shape(path: Path) -> list[tuple[str, list[str]]]:
    book = load_workbook(path, data_only=True)
    shape = []
    for name in book.sheetnames:
        header = [c for c in next(book[name].iter_rows(values_only=True)) if c is not None]
        shape.append((name, [str(c).strip() for c in header]))
    return shape


# ------------------------------------------------------------------ primitives
def make_money(places: int):
    quantum = Decimal(1).scaleb(-places)

    def money(value) -> Decimal:
        return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)

    return money


def make_calendar(holidays: set[date]):
    def business(d: date) -> bool:
        return d.weekday() < 5 and d not in holidays

    def distance(a: date, b: date) -> int:
        if a > b:
            a, b = b, a
        count, cur = 0, a
        while cur < b:
            cur += timedelta(days=1)
            if business(cur):
                count += 1
        return count

    return distance


def normalise_reference(token: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", token).upper()
    return re.sub(r"0*(\d+)", lambda m: m.group(1), cleaned)


def tokens_of(reference: str) -> list[str]:
    parts = [p for p in re.split(r"[+,]", reference or "") if p.strip()]
    out = [normalise_reference(p) for p in parts]
    return [t for t in out if t]


def normalise_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip().upper()


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ------------------------------------------------------------------ records
def read_statement(path: Path) -> list[dict]:
    lines = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lines.append({
                "Txn_ID": row["Txn_ID"].strip(),
                "Value_Date": datetime.strptime(row["Value_Date"].strip(), "%d/%m/%Y").date(),
                "Channel": row["Channel"].strip().upper(),
                "Counterparty": row["Counterparty"].strip(),
                "Reference": row["Reference"].strip(),
                "Amount": Decimal(row["Amount"].strip()),
            })
    return lines


def read_ledger(path: Path) -> list[dict]:
    book = load_workbook(path, data_only=True)
    for name in book.sheetnames:
        rows = list(book[name].iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        if "Ledger_ID" not in header:
            continue
        index = {key: header.index(key) for key in header if key}
        entries = []
        for row in rows[1:]:
            if row is None or all(c is None for c in row):
                continue
            entries.append({
                "Ledger_ID": str(row[index["Ledger_ID"]]).strip(),
                "Vendor": str(row[index["Vendor"]]).strip(),
                "Invoice_Ref": str(row[index["Invoice_Ref"]]).strip(),
                "Due_Date": as_date(row[index["Due_Date"]]),
                "Amount_Due": Decimal(str(row[index["Amount_Due"]])),
                "Status": str(row[index["Status"]]).strip().upper(),
            })
        return entries
    raise SystemExit("ap_ledger.xlsx has no sheet carrying a Ledger_ID column")


# ------------------------------------------------------------------ reconciliation
def reconcile(workspace: Path) -> dict:
    rules = read_procedure(workspace / "sop" / "Reconciliation_Procedure.docx")
    shape = read_shape(workspace / "sop" / "Format_Example.xlsx")
    money = make_money(rules["places"])
    distance = make_calendar(rules["holidays"])
    sentinel = rules["sentinel"]

    statement = read_statement(workspace / "bank_statement.csv")
    ledger = read_ledger(workspace / "ap_ledger.xlsx")

    all_vendors = {normalise_name(e["Vendor"]) for e in ledger}
    in_scope_ledger = [
        e for e in ledger
        if e["Status"] in rules["statuses_in"]
        and rules["window_start"] <= e["Due_Date"] <= rules["window_end"]
    ]
    by_reference: dict[str, list[dict]] = {}
    for entry in in_scope_ledger:
        by_reference.setdefault(normalise_reference(entry["Invoice_Ref"]), []).append(entry)

    lines = [ln for ln in statement if ln["Channel"] in rules["channels_in"]]
    lines.sort(key=lambda ln: (ln["Value_Date"], ln["Txn_ID"]))
    for line in lines:
        line["tokens"] = tokens_of(line["Reference"])
        line["magnitude"] = money(abs(line["Amount"]))

    # 6.3 -- reversal pairs are taken out before anything else is decided.
    reversed_lines: set[str] = set()
    groups: dict[tuple, list[dict]] = {}
    for line in lines:
        if line["tokens"]:
            groups.setdefault((tuple(sorted(line["tokens"])), line["magnitude"]), []).append(line)
    for group in groups.values():
        debits = [ln for ln in group if ln["Amount"] < 0]
        credits = [ln for ln in group if ln["Amount"] > 0]
        for debit, credit in zip(debits, credits):
            reversed_lines.add(debit["Txn_ID"])
            reversed_lines.add(credit["Txn_ID"])

    settled: dict[str, str] = {}          # Ledger_ID -> settling Txn_ID
    matched: list[dict] = []
    unmatched_bank: list[dict] = []
    ambiguous_entries: set[str] = set()
    reversed_entries: set[str] = set()
    amount_failed: set[str] = set()
    date_failed: set[str] = set()

    def reject(line, reason, candidates=()):
        unmatched_bank.append({
            "Txn_ID": line["Txn_ID"],
            "Value_Date": line["Value_Date"].isoformat(),
            "Counterparty": line["Counterparty"],
            "Reference": line["Reference"] if line["Reference"].strip() else sentinel,
            "Amount": float(money(line["Amount"])),
            "Reason": reason,
            "Candidate_Ledger_IDs": "; ".join(sorted(candidates)) if candidates else sentinel,
        })

    for line in lines:
        if line["Txn_ID"] in reversed_lines:
            for token in line["tokens"]:
                for entry in by_reference.get(token, []):
                    reversed_entries.add(entry["Ledger_ID"])
            reject(line, "REVERSED")
            continue

        if normalise_name(line["Counterparty"]) not in all_vendors:
            reject(line, "VENDOR_NOT_ON_LEDGER")
            continue

        if not line["tokens"]:
            reject(line, "NO_REFERENCE_MATCH")
            continue

        resolved = [by_reference.get(token, []) for token in line["tokens"]]
        if any(len(c) == 0 for c in resolved):
            reject(line, "NO_REFERENCE_MATCH")
            continue
        if any(len(c) > 1 for c in resolved):
            candidates = {e["Ledger_ID"] for group in resolved for e in group}
            for ledger_id in candidates:
                ambiguous_entries.add(ledger_id)
            reject(line, "AMBIGUOUS_MATCH", candidates)
            continue

        entries = [group[0] for group in resolved]
        ids = [e["Ledger_ID"] for e in entries]
        if len(set(ids)) != len(ids) or len({e["Vendor"] for e in entries}) != 1:
            reject(line, "NO_REFERENCE_MATCH")
            continue

        ledger_amount = money(sum(e["Amount_Due"] for e in entries))
        difference = money(line["magnitude"] - ledger_amount)
        if abs(difference) > rules["amount_tolerance"]:
            amount_failed.update(ids)
            reject(line, "AMOUNT_OUT_OF_TOLERANCE")
            continue

        gap = max(distance(e["Due_Date"], line["Value_Date"]) for e in entries)
        if gap > rules["date_tolerance"]:
            date_failed.update(ids)
            reject(line, "DATE_OUT_OF_TOLERANCE")
            continue

        if any(i in settled for i in ids):
            reject(line, "DUPLICATE_PAYMENT")
            continue

        for i in ids:
            settled[i] = line["Txn_ID"]
        matched.append({
            "Txn_ID": line["Txn_ID"],
            "Value_Date": line["Value_Date"].isoformat(),
            "Ledger_IDs": "; ".join(sorted(ids)),
            "Vendor": entries[0]["Vendor"],
            "Bank_Amount": float(line["magnitude"]),
            "Ledger_Amount": float(ledger_amount),
            "Amount_Difference": float(difference),
            "Date_Gap_Days": gap,
            "Match_Type": "ONE_TO_ONE" if len(ids) == 1 else "ONE_TO_MANY",
        })

    unmatched_ledger = []
    for entry in in_scope_ledger:
        ledger_id = entry["Ledger_ID"]
        if ledger_id in settled:
            continue
        if ledger_id in ambiguous_entries:
            reason = "AMBIGUOUS_MATCH"
        elif ledger_id in reversed_entries:
            reason = "PAYMENT_REVERSED"
        elif ledger_id in amount_failed:
            reason = "AMOUNT_OUT_OF_TOLERANCE"
        elif ledger_id in date_failed:
            reason = "DATE_OUT_OF_TOLERANCE"
        else:
            reason = "NO_BANK_LINE"
        unmatched_ledger.append({
            "Ledger_ID": ledger_id,
            "Vendor": entry["Vendor"],
            "Invoice_Ref": entry["Invoice_Ref"],
            "Due_Date": entry["Due_Date"].isoformat(),
            "Amount_Due": float(money(entry["Amount_Due"])),
            "Reason": reason,
        })

    matched.sort(key=lambda r: r["Txn_ID"])
    unmatched_bank.sort(key=lambda r: r["Txn_ID"])
    unmatched_ledger.sort(key=lambda r: r["Ledger_ID"])
    return {"shape": shape, "output": rules["output"],
            "Matched": matched, "UnmatchedBank": unmatched_bank,
            "UnmatchedLedger": unmatched_ledger}


def solve(workspace: Path) -> None:
    result = reconcile(workspace)
    book = Workbook()
    for index, (title, columns) in enumerate(result["shape"]):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        sheet.append(columns)
        for row in result[title]:
            sheet.append([row[column] for column in columns])
    book.save(workspace / result["output"])
    print(f"matched {len(result['Matched'])}, "
          f"unmatched bank {len(result['UnmatchedBank'])}, "
          f"unmatched ledger {len(result['UnmatchedLedger'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
