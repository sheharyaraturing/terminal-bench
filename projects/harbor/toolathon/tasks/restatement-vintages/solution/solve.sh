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
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

WORD_TO_PLACES = {"one": 1, "two": 2, "three": 3, "four": 4}
MODES = {"half-up": ROUND_HALF_UP, "half-to-even": ROUND_HALF_EVEN}

class Policy:

    def __init__(self, text: str) -> None:
        self.text = text
        self.cutoff = self._one(r"reporting cutoff for this round is \*\*(\d{4}-\d{2}-\d{2})\*\*")
        self.scope_status = self._one(r"periods whose `close_status` is `([a-z_]+)`")
        self.basis = self._one(r"its `basis` is `([a-z_]+)`")
        pair = self._match(r"its `vintage_type` is `([a-z]+)` or `([a-z]+)`")
        self.publishable = {pair.group(1), pair.group(2)}
        self.sentinel = self._one(r"every value column\s+carries the literal `([A-Z]+)`")
        self.defined_marker = self._one(r"`Undefined_Reason` carries the literal `([A-Z]+)`")
        self.sheet = self._one(r"one sheet named `([A-Za-z_]+)`")

        rounding = self._match(
            r"Round \*\*(half-up|half-to-even) to (one|two|three|four) decimal place"
        )
        self.rounding = MODES[rounding.group(1)]
        self.places = WORD_TO_PLACES[rounding.group(2)]
        self.quantum = Decimal(1).scaleb(-self.places)

        self.reason_order = self._ranked(self._section("6."))
        self.bucket_order = self._ranked(self._section("8."))
        self.shape = json.loads(self._one(r"```json\n(.*?)\n```", re.S))

    # -- parsing helpers ----------------------------------------------------
    def _match(self, pattern: str, flags: int = 0):
        found = re.search(pattern, self.text, flags)
        if not found:
            raise SystemExit(f"policy parse failed; no match for {pattern!r}")
        return found

    def _one(self, pattern: str, flags: int = 0) -> str:
        return self._match(pattern, flags).group(1)

    def _section(self, number: str) -> str:
        parts = re.split(r"^## ", self.text, flags=re.M)
        for part in parts:
            if part.startswith(number):
                return part
        raise SystemExit(f"policy parse failed; no section {number}")

    @staticmethod
    def _ranked(section: str) -> list[str]:
        rows = re.findall(r"^\|\s*\S+\s*\|\s*`([a-z_]+)`\s*\|", section, re.M)
        if not rows:
            raise SystemExit("policy parse failed; a precedence table read empty")
        return rows

def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

def solve(ws: Path) -> None:
    policy = Policy((ws / "metrics" / "Reporting_Policy.md").read_text(encoding="utf-8"))

    example = load_workbook(ws / "metrics" / "Format_Example.xlsx", data_only=True)
    headers = [
        str(cell).strip()
        for cell in next(example[policy.sheet].iter_rows(values_only=True))
        if cell is not None
    ]
    example.close()

    calendar = load_rows(ws / "close_calendar.csv")
    covered = [r["period"] for r in calendar if r["close_status"] == policy.scope_status]
    in_scope = set(covered)

    filings = load_rows(ws / "financials.csv")

    def publishable(row: dict[str, str]) -> bool:
        return (
            row["basis"] == policy.basis
            and row["vintage_type"] in policy.publishable
            and row["net_revenue_usd"].strip() != ""
        )

    tests = {
        "out_of_scope_period": lambda r: r["reported_for_period"] not in in_scope,
        "management_basis": lambda r: r["basis"] != policy.basis,
        "after_cutoff": lambda r: r["as_of_date"] > policy.cutoff,
        "no_amount": lambda r: r["net_revenue_usd"].strip() == "",
        "preliminary": lambda r: r["vintage_type"] not in policy.publishable,
    }
    order = [name for name in policy.bucket_order if name in tests]
    included_name = next(n for n in policy.bucket_order if n not in tests)

    counts = {name: 0 for name in policy.bucket_order}
    for row in filings:
        landed = next((name for name in order if tests[name](row)), included_name)
        counts[landed] += 1

    sheet_rows: list[list[object]] = []
    total = 0
    defined = 0
    for period in covered:
        rows = [r for r in filings if r["reported_for_period"] == period]
        pub = [r for r in rows if publishable(r)]
        selectable = sorted(
            (r for r in pub if r["as_of_date"] <= policy.cutoff),
            key=lambda r: r["as_of_date"],
        )

        verdicts = {
            "no_records": not rows,
            "no_reportable_vintage": not pub,
            "all_vintages_after_cutoff": not selectable,
        }
        reason = next((c for c in policy.reason_order if verdicts.get(c)), None)
        if reason is not None:
            sheet_rows.append([period] + [policy.sentinel] * 5 + [reason])
            continue

        original, latest = selectable[0], selectable[-1]
        latest_amount = int(latest["net_revenue_usd"])
        original_amount = int(original["net_revenue_usd"])
        pct = (
            (Decimal(latest_amount) - Decimal(original_amount))
            / Decimal(original_amount)
            * Decimal(100)
        ).quantize(policy.quantum, rounding=policy.rounding)
        sheet_rows.append([
            period,
            latest_amount,
            latest["as_of_date"],
            original_amount,
            original["as_of_date"],
            float(pct),
            policy.defined_marker,
        ])
        total += latest_amount
        defined += 1

    book = Workbook()
    sheet = book.active
    sheet.title = policy.sheet
    sheet.append(headers)
    for row in sheet_rows:
        sheet.append(row)
    book.save(ws / "vintage_report.xlsx")

    workings = {
        "metric": policy.shape["metric"],
        "reporting_cutoff": policy.cutoff,
        "value": total,
        "undefined": False,
        "undefined_reason": None,
        "denominator": None,
        "periods_defined": defined,
        "periods_undefined": len(sheet_rows) - defined,
        "population": {
            "included": counts[included_name],
            "excluded": {name: counts[name] for name in order},
        },
    }
    (ws / "workings.json").write_text(json.dumps(workings, indent=2) + "\n", encoding="utf-8")

    print(f"cutoff {policy.cutoff}  covered {len(covered)}  "
          f"defined {defined}  undefined {len(sheet_rows) - defined}")
    print(f"value {total}  included {counts[included_name]}  "
          f"excluded {[(n, counts[n]) for n in order]}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
