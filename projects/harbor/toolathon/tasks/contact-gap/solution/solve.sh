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
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook, load_workbook

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
MODES = {"half-up": ROUND_HALF_UP, "half-even": ROUND_HALF_EVEN}

class Spec:

    def __init__(self, workspace: Path) -> None:
        text = (workspace / "metrics" / "Definitions.md").read_text(encoding="utf-8")

        m = re.search(r"reporting period for this extract is\s+\*\*(\d{4}-\d{2}-\d{2})\s+to\s+"
                      r"(\d{4}-\d{2}-\d{2})\*\*", text)
        if not m:
            raise SystemExit("Definitions.md does not state the reporting period")
        self.start, self.end = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))

        m = re.search(r"sentinel string\s+`([A-Za-z_]+)`", text)
        if not m:
            raise SystemExit("Definitions.md does not name the undefined sentinel")
        self.sentinel = m.group(1)

        codes = re.findall(r"`([A-Z][A-Z_]+)`", text.split("## 7.")[1].split("## 8.")[0])
        wanted = [c for c in codes if c != self.sentinel]
        self.ambiguous = next(c for c in wanted if "AMBIG" in c)
        self.missing = next(c for c in wanted if "MISSING" in c)
        self.none = next(c for c in wanted if c not in (self.ambiguous, self.missing))

        m = re.search(r"\*\*(\w+) decimal places, rounded (half-up|half-even)\*\*", text)
        if not m:
            raise SystemExit("Definitions.md does not state the rounding convention")
        self.places, self.rounding = WORDS[m.group(1).lower()], MODES[m.group(2)]

        m = re.search(r"```json\n(\{.*?\})\n```", text, re.DOTALL)
        if not m:
            raise SystemExit("Definitions.md does not carry the workings skeleton")
        self.skeleton = json.loads(m.group(1))
        if date.fromisoformat(self.skeleton["period_start"]) != self.start:
            raise SystemExit("Definitions.md contradicts itself about the period")

        example = load_workbook(workspace / "metrics" / "Format_Example.xlsx")
        sheet = example.worksheets[0]
        self.sheet_name = sheet.title
        self.columns = [str(c).strip() for c in next(sheet.iter_rows(values_only=True))
                        if c is not None]

    def in_period(self, day: date) -> bool:
        return self.start <= day <= self.end

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]

def solve(workspace: Path) -> None:
    spec = Spec(workspace)

    # --- section 3: the population is distinct customer_id, repeats collapsed
    names: dict[str, list[str]] = defaultdict(list)
    segments: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    for row in read_csv(workspace / "data" / "customers.csv"):
        cid = row["customer_id"]
        if not cid:
            continue
        if cid not in names:
            order.append(cid)
        names[cid].append(row["customer_name"])
        segments[cid].append(row["segment"])
    population = set(order)

    # --- section 4: first matching test wins, and the order is stated
    counts = {"out_of_period_tickets": 0, "orphan_tickets": 0, "soft_deleted_tickets": 0}
    contacted: set[str] = set()
    for row in read_csv(workspace / "data" / "tickets.csv"):
        opened = date.fromisoformat(row["opened_at"])
        if not spec.in_period(opened):
            counts["out_of_period_tickets"] += 1
            continue
        cid = row["customer_id"]
        if not cid or cid not in population:
            counts["orphan_tickets"] += 1
            continue
        if row["deleted_at"]:
            counts["soft_deleted_tickets"] += 1
            continue
        contacted.add(cid)

    without = sorted(population - contacted)

    # --- section 7: flag what the extract cannot settle, never guess it
    rows = []
    for cid in without:
        distinct_names = sorted({n for n in names[cid] if n})
        distinct_segments = sorted({s for s in segments[cid] if s})
        name = distinct_names[0] if len(distinct_names) == 1 else ""
        segment = distinct_segments[0] if len(distinct_segments) == 1 else ""
        if len(distinct_names) > 1:
            rows.append([cid, spec.sentinel, segment or spec.sentinel, spec.ambiguous])
        elif not segment:
            rows.append([cid, name, spec.sentinel, spec.missing])
        else:
            rows.append([cid, name, segment, spec.none])

    book = Workbook()
    sheet = book.active
    sheet.title = spec.sheet_name
    sheet.append(spec.columns)
    for row in rows:
        sheet.append(row)
    book.save(workspace / "no_contact.xlsx")

    total, with_contact = len(population), len(population & contacted)
    quantum = Decimal(1).scaleb(-spec.places)
    rate = (Decimal(with_contact) / Decimal(total)).quantize(quantum, rounding=spec.rounding)

    workings = dict(spec.skeleton)
    workings.update({
        "customers_total": total,
        "customers_with_contact": with_contact,
        "value": len(without),
        "contact_rate": float(rate),
        **counts,
    })
    (workspace / "workings.json").write_text(json.dumps(workings, indent=2) + "\n")

    print(f"population {total}, with contact {with_contact}, without {len(without)}")
    print(f"contact_rate {rate}  " + "  ".join(f"{k} {v}" for k, v in counts.items()))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
