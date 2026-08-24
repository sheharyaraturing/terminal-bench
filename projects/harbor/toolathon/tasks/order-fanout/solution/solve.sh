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

from openpyxl import Workbook, load_workbook

CENT = Decimal("0.01")


def rules(doc: str) -> dict:
    def need(pattern: str) -> re.Match:
        found = re.search(pattern, doc)
        if not found:
            raise SystemExit(f"Definitions.md never states: {pattern}")
        return found

    start, end = need(
        r"`order_date`\s+between\s+`(\d{4}-\d{2}-\d{2})`\s+and\s+`(\d{4}-\d{2}-\d{2})`"
    ).groups()
    status_clause = need(r"`cancelled_or_draft`[^\n]*?`status`\s+is\s+([^\n.]+)").group(1)
    need(r"\*\*half-up\*\* rounding")
    outputs = re.findall(r"Write `([\w.]+)` in the workspace root", doc)
    if len(outputs) < 2:
        raise SystemExit("Definitions.md names fewer than two output files")

    return {
        "start": start,
        "end": end,
        "internal": need(r"`account_type`\s*=\s*`([a-z_]+)`").group(1),
        "dropped_statuses": tuple(re.findall(r"`([a-z_]+)`", status_clause)),
        "sentinel": need(r"Report the sentinel\s+`([A-Za-z_]+)`").group(1),
        "reason": need(r"and\s+`([a-z_]+)`\s+in\s+`Undefined_Reason`").group(1),
        "currency": need(r"reporting currency is \*\*([A-Z]{3})\*\*").group(1),
        "sheet": need(r"sheet named `([A-Za-z0-9_ ]+)`").group(1),
        "metric": need(r"the string `([a-z_]+)`").group(1),
        "sheet_file": outputs[0],
        "workings_file": outputs[1],
    }


def columns(example: Path) -> list[str]:
    header = next(
        load_workbook(example, data_only=True).active.iter_rows(
            min_row=1, max_row=1, values_only=True
        )
    )
    return [str(c).strip() for c in header if c is not None]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def half_up(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def solve(ws: Path) -> dict:
    metrics = ws / "metrics"
    rule = rules((metrics / "Definitions.md").read_text(encoding="utf-8"))
    header = columns(metrics / "Format_Example.xlsx")

    customers = read_csv(ws / "data" / "customers.csv")
    orders = read_csv(ws / "data" / "orders.csv")
    lines = read_csv(ws / "data" / "order_lines.csv")

    account_type = {c["customer_id"]: c["account_type"] for c in customers}
    name = {c["customer_id"]: c["customer_name"] for c in customers}

    # §3: first reason that matches wins, so the three counts partition the excluded rows.
    excluded = {"internal_account": 0, "out_of_period": 0, "cancelled_or_draft": 0}
    in_scope: list[dict[str, str]] = []
    for order in orders:
        if account_type.get(order["customer_id"]) == rule["internal"]:
            excluded["internal_account"] += 1
        elif not (rule["start"] <= order["order_date"] <= rule["end"]):
            excluded["out_of_period"] += 1
        elif order["status"] in rule["dropped_statuses"]:
            excluded["cancelled_or_draft"] += 1
        else:
            in_scope.append(order)

    scope_ids = {o["order_id"] for o in in_scope}
    rows_after_join = sum(1 for line in lines if line["order_id"] in scope_ids)

    grouped: dict[str, list[dict[str, str]]] = {}
    for order in in_scope:
        grouped.setdefault(order["customer_id"], []).append(order)

    book = Workbook()
    sheet = book.active
    sheet.title = rule["sheet"]
    sheet.append(header)

    total = Decimal("0")
    for cid in sorted(grouped):
        group = grouped[cid]
        currencies = {o["currency"] for o in group}
        if len(currencies) > 1:
            # §5 restraint: undefined is the answer, not a sum across currencies.
            sheet.append(
                [cid, name[cid], rule["sentinel"], len(group), rule["sentinel"], rule["reason"]]
            )
            continue
        currency = currencies.pop()
        # §4: each order contributes its own total once, whatever its line count.
        revenue = half_up(sum((Decimal(o["order_total"]) for o in group), Decimal("0")))
        sheet.append([cid, name[cid], currency, len(group), float(revenue), ""])
        if currency == rule["currency"]:
            total += revenue
    book.save(ws / rule["sheet_file"])

    workings = {
        "metric": rule["metric"],
        "value": float(half_up(total)),
        "undefined": False,
        "undefined_reason": None,
        "denominator": None,
        "population": {
            "included": len(in_scope),
            "excluded": excluded,
            "rows_before_join": len(in_scope),
            "rows_after_join": rows_after_join,
        },
    }
    (ws / rule["workings_file"]).write_text(
        json.dumps(workings, indent=2) + "\n", encoding="utf-8"
    )
    return workings


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    a = ap.parse_args()
    result = solve(a.workspace)
    population = result["population"]
    print(f"revenue {result['value']} over {population['included']} in-scope orders")
    print(f"rows before/after join {population['rows_before_join']}/{population['rows_after_join']}")
PY

echo "Done!"
