#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook

INVOICE_COLUMNS = {"date", "vendor", "invoice", "amount"}

def _key(name) -> str:
    """Normalised form used to match a ledger spelling to a registered vendor."""
    return re.sub(r"\s+", " ", str(name)).strip().casefold()

def _header(row) -> list[str]:
    return [str(c).strip().lower() if c is not None else "" for c in row]

def registered_names(ws: Path) -> dict[str, str]:
    """Every spelling a vendor may be keyed under, mapped to its registered name."""
    sheet = load_workbook(ws / "vendor_master.xlsx", data_only=True).active
    rows = list(sheet.iter_rows(values_only=True))
    header = _header(rows[0])
    vi = header.index("vendor")
    ai = header.index("also known as") if "also known as" in header else None

    names: dict[str, str] = {}
    for r in rows[1:]:
        if r is None or r[vi] is None:
            continue
        registered = str(r[vi]).strip()
        names[_key(registered)] = registered
        if ai is not None and r[ai]:
            for alias in str(r[ai]).split(";"):
                if alias.strip():
                    names[_key(alias)] = registered
    return names

def monthly_totals(ws: Path) -> dict[str, dict[str, float]]:
    names = registered_names(ws)
    totals: dict[str, dict[str, float]] = defaultdict(dict)

    for book in sorted((ws / "ledger").glob("*.xlsx")):
        month = book.stem
        seen: set[str] = set()
        for sheet in load_workbook(book, data_only=True).worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            header = _header(rows[0])
            if not INVOICE_COLUMNS <= set(header):
                continue  # a recap tab, not a payment run
            vi, ii, ai = header.index("vendor"), header.index("invoice"), header.index("amount")
            for r in rows[1:]:
                if r is None or r[vi] is None:
                    continue
                invoice = str(r[ii]).strip()
                if invoice in seen:
                    continue  # the same invoice re-keyed into a later run
                seen.add(invoice)
                vendor = names.get(_key(r[vi]), str(r[vi]).strip())
                totals[vendor][month] = totals[vendor].get(month, 0) + float(r[ai])
    return totals

def build(totals: dict[str, dict[str, float]]):
    flagged, thin = [], []
    for vendor, series in totals.items():
        months = sorted(series)
        values = [series[m] for m in months]
        if len(values) < 2:
            thin.append((vendor, months[0], values[0]))
            continue
        mean = st.fmean(values)
        threshold = mean + 2 * st.pstdev(values)
        for m in months:
            if series[m] > threshold:
                flagged.append((vendor, m, series[m], round(mean, 2), round(series[m] - mean, 2)))
    flagged.sort(key=lambda r: (r[0], r[1]))
    thin.sort()
    return flagged, thin

def write(ws: Path, flagged, thin) -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Exceptions"
    sheet.append(["Vendor", "Month", "Amount", "Baseline", "Deviation", "Status"])
    for vendor, month, amount, baseline, deviation in flagged:
        sheet.append([vendor, month, amount, baseline, deviation, "FLAGGED"])
    for vendor, month, amount in thin:
        sheet.append([vendor, month, amount, "N/A", "N/A", "INSUFFICIENT_HISTORY"])
    sheet.append(["Total flagged:", len(flagged)])
    wb.save(ws / "exception_register.xlsx")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace)
    flagged, thin = build(monthly_totals(ws))
    write(ws, flagged, thin)
    print(f"flagged {len(flagged)}, insufficient history {len(thin)}")

if __name__ == "__main__":
    main()
PY

echo "Done!"
