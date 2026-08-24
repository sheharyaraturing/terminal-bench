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
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook

CENT = Decimal("0.01")

# ---------------------------------------------------------------- the policy
def read_policy(text: str) -> dict:
    def one(pattern: str, *, group: int = 1, flags: int = 0) -> str:
        m = re.search(pattern, text, flags)
        if not m:
            raise SystemExit(f"policy does not state: {pattern}")
        return m.group(group).strip()

    start = one(r"Reporting period:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*")
    end = one(r"Reporting period:.*?to\s*\*\*(\d{4}-\d{2}-\d{2})\*\*")
    columns_line = one(r"in this order:\s*\n\s*\n((?:`[A-Za-z_]+`(?:,\s*)?)+)", flags=re.S)

    reasons = {
        "no_row": one(r"\|\s*`(\w+)`\s*\|\s*the snapshot carries no row at all"),
        "no_earlier": one(r"\|\s*`(\w+)`\s*\|\s*the snapshot carries the currency but publishes"),
    }
    outputs = re.findall(r"^### 7\.\d\s+`([^`]+)`", text, flags=re.M)
    if len(outputs) != 2:
        raise SystemExit("policy does not name exactly two deliverables")

    return {
        "period": (date.fromisoformat(start), date.fromisoformat(end)),
        "ledger": one(r"`([\w./-]+\.csv)` is the trading record"),
        "snapshot": one(r"Authoritative snapshot:\s*`([^`]+)`"),
        "status": one(r"its `status` is `(\w+)`"),
        "sheet": one(r"holding a sheet named \*\*`([^`]+)`\*\*"),
        "columns": re.findall(r"`([A-Za-z_]+)`", columns_line),
        "reporting_currency": one(r"group reporting currency is \*\*(\w{3})\*\*"),
        "not_applicable": one(r"its `Rate_Basis` as `(\w+)`"),
        "published": one(r"\|\s*`(\w+)`\s*\|\s*the snapshot publishes this currency"),
        "carried": one(r"\|\s*`(\w+)`\s*\|\s*nothing was published that date"),
        "sentinel": one(r"write the literal string `(\w+)` in `Rate_Date`"),
        "reasons": reasons,
        "workbook": outputs[0],
        "workings": outputs[1],
    }

# ---------------------------------------------------------------- the data
def read_snapshot(path: Path) -> dict[str, list[tuple[date, Decimal]]]:
    series: dict[str, list[tuple[date, Decimal]]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            series.setdefault(row["currency"], []).append(
                (date.fromisoformat(row["quote_date"]), Decimal(row["usd_per_unit"]))
            )
    for quotes in series.values():
        quotes.sort()
    return series

def latest_on_or_before(quotes: list[tuple[date, Decimal]], when: date):
    found = None
    for quote_date, rate in quotes:
        if quote_date > when:
            break
        found = (quote_date, rate)
    return found

# ---------------------------------------------------------------- the restatement
def solve(workspace: Path) -> None:
    policy = read_policy((workspace / "metrics" / "FX_Policy.md").read_text(encoding="utf-8"))
    start, end = policy["period"]
    series = read_snapshot(workspace / policy["snapshot"])

    with (workspace / policy["ledger"]).open(newline="", encoding="utf-8") as fh:
        ledger = list(csv.DictReader(fh))

    population = [
        r for r in ledger
        if r["status"].strip() == policy["status"]
        and start <= date.fromisoformat(r["txn_date"].strip()) <= end
    ]
    population.sort(key=lambda r: r["txn_id"])

    book = Workbook()
    sheet = book.active
    sheet.title = policy["sheet"]
    sheet.append(policy["columns"])

    sentinel = policy["sentinel"]
    total = Decimal("0.00")
    by_currency: dict[str, int] = {}
    carried = 0
    by_reason = {policy["reasons"]["no_row"]: 0, policy["reasons"]["no_earlier"]: 0}

    for record in population:
        code = record["currency"].strip()
        when = date.fromisoformat(record["txn_date"].strip())
        amount = Decimal(record["amount"].strip())
        by_currency[code] = by_currency.get(code, 0) + 1

        if code == policy["reporting_currency"]:
            rate, rate_date = Decimal("1.00000000"), when.isoformat()
            usd = amount.quantize(CENT, rounding=ROUND_HALF_UP)
            basis = policy["not_applicable"]
        elif code not in series:
            rate = rate_date = usd = sentinel
            basis = policy["reasons"]["no_row"]
            by_reason[basis] += 1
        else:
            quote = latest_on_or_before(series[code], when)
            if quote is None:
                rate = rate_date = usd = sentinel
                basis = policy["reasons"]["no_earlier"]
                by_reason[basis] += 1
            else:
                quoted_on, rate = quote
                rate_date = quoted_on.isoformat()
                usd = (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)
                basis = policy["published"] if quoted_on == when else policy["carried"]
                if basis == policy["carried"]:
                    carried += 1

        if usd != sentinel:
            total += usd
        sheet.append([
            record["txn_id"], code, float(amount.quantize(CENT, rounding=ROUND_HALF_UP)),
            rate_date,
            rate if isinstance(rate, str) else float(rate),
            usd if isinstance(usd, str) else float(usd),
            basis,
        ])

    book.save(workspace / policy["workbook"])

    workings = {
        "metric": "usd_revenue",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_usd_revenue": float(total),
        "transactions_by_currency": dict(sorted(by_currency.items())),
        "carried_forward_count": carried,
        "undefined_count": sum(by_reason.values()),
        "undefined_by_reason": by_reason,
    }
    (workspace / policy["workings"]).write_text(json.dumps(workings, indent=2) + "\n",
                                                encoding="utf-8")
    print(f"restated {len(population)} transactions, total {total}, "
          f"{carried} carried forward, {sum(by_reason.values())} undefined")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
