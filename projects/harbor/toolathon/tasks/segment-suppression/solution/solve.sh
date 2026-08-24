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
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def need(pattern: str, text: str, flags: int = 0) -> re.Match:
    m = re.search(pattern, text, flags)
    if not m:
        raise SystemExit(f"Definitions.md does not state: {pattern}")
    return m


def read_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    spec: dict = {}

    m = need(r"runs from \*\*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\*\*", text)
    spec["period"] = (m.group(1), m.group(2))

    spec["data_dir"] = need(r"[Tt]wo extracts under `([A-Za-z0-9_]+)/`", text).group(1)
    spec["dimension"] = need(r"\| `([A-Za-z0-9_]+\.csv)` \| one row per segment", text).group(1)
    spec["facts"] = need(r"\| `([A-Za-z0-9_]+\.csv)` \| one row per exported visit", text).group(1)

    spec["register"] = need(r"its `segment_id` appears in `([A-Za-z0-9_]+\.csv)`", text).group(1)
    spec["excluded_channel"] = need(r"its `channel` is not `([a-z_]+)`", text).group(1)
    spec["kept_status"] = need(r"its `status` is `([a-z_]+)`", text).group(1)
    spec["converted"] = need(r"whose `outcome` is `([a-z_]+)`", text).group(1)

    order_block = text.split("takes it and the others are not counted:", 1)[1]
    spec["precedence"] = re.findall(r"^\s*\d+\.\s+`([a-z_]+)`\s*$", order_block, re.M)
    if len(spec["precedence"]) != 5:
        raise SystemExit(f"expected five exclusion reasons, parsed {spec['precedence']}")

    m = need(r"rounded to \*\*(\w+) decimal places, ([a-z-]+)\*\*", text)
    spec["places"] = WORDS[m.group(1).lower()]
    spec["rounding"] = m.group(2).lower()
    if spec["rounding"] != "half-up":
        raise SystemExit(f"unhandled rounding mode {spec['rounding']!r}")

    spec["threshold"] = int(
        need(r"published only when the segment's denominator is \*\*(\d+) or more\*\*", text).group(1)
    )

    m = need(r"\| Denominator is 0 \| `([A-Z_]+)` \| `([A-Z_]+)` \|", text)
    spec["sentinel"], spec["no_base"] = m.group(1), m.group(2)
    m = need(r"\| Denominator is 1 to (\d+) \| `([A-Z_]+)` \| `([A-Z_]+)` \|", text)
    if int(m.group(1)) != spec["threshold"] - 1 or m.group(2) != spec["sentinel"]:
        raise SystemExit("the suppression table and the threshold sentence disagree")
    spec["low_base"] = m.group(3)
    spec["ok"] = need(r"\| Denominator is \d+ or more \| [^|]+\| `([A-Z_]+)` \|", text).group(1)

    spec["workbook"] = need(r"Write `([A-Za-z0-9_]+\.xlsx)` to the workspace root", text).group(1)
    spec["sheet"] = need(r"with a sheet named `([A-Za-z0-9_]+)`", text).group(1)
    spec["total"] = need(r"`Segment` = `([A-Z]+)`", text).group(1)

    block = text.split("The columns, in this order:", 1)[1].split("One row per segment", 1)[0]
    spec["columns"] = re.findall(r"^\| `([A-Za-z]+)` \|", block, re.M)
    if len(spec["columns"]) != 5:
        raise SystemExit(f"expected five output columns, parsed {spec['columns']}")

    spec["workings_file"] = need(r"Write `([A-Za-z0-9_]+\.json)` to the workspace root", text).group(1)
    spec["workings"] = json.loads(need(r"```json\n(.*?)\n```", text, re.S).group(1))
    return spec


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def rate(numerator: int, denominator: int, places: int) -> Decimal:
    pct = Decimal(numerator) * 100 / Decimal(denominator)
    return pct.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def solve(ws: Path) -> None:
    spec = read_spec(ws / "metrics" / "Definitions.md")
    data = ws / spec["data_dir"]

    registered = OrderedDict()
    for row in rows(data / spec["dimension"]):
        registered[row["segment_id"].strip()] = row

    start, end = spec["period"]
    seen: set[str] = set()
    excluded = {reason: 0 for reason in spec["precedence"]}
    numerator = {seg: 0 for seg in registered}
    denominator = {seg: 0 for seg in registered}
    read = 0

    tests = {
        "duplicate_visit_id": lambda r: r["visit_id"].strip() in seen,
        "unknown_segment": lambda r: r["segment_id"].strip() not in registered,
        "outside_period": lambda r: not (start <= r["visit_date"].strip() <= end),
        "internal_channel": lambda r: r["channel"].strip() == spec["excluded_channel"],
        "void_status": lambda r: r["status"].strip() != spec["kept_status"],
    }

    for row in rows(data / spec["facts"]):
        read += 1
        reason = next((r for r in spec["precedence"] if tests[r](row)), None)
        seen.add(row["visit_id"].strip())
        if reason is not None:
            excluded[reason] += 1
            continue
        segment = row["segment_id"].strip()
        denominator[segment] += 1
        if row["outcome"].strip() == spec["converted"]:
            numerator[segment] += 1

    disposition = {}
    for segment in registered:
        if denominator[segment] == 0:
            disposition[segment] = spec["no_base"]
        elif denominator[segment] < spec["threshold"]:
            disposition[segment] = spec["low_base"]
        else:
            disposition[segment] = spec["ok"]

    published = [s for s in registered if disposition[s] == spec["ok"]]
    total_num = sum(numerator[s] for s in published)
    total_den = sum(denominator[s] for s in published)
    if total_den == 0:
        total_rate, total_reason = spec["sentinel"], spec["no_base"]
    elif total_den < spec["threshold"]:
        total_rate, total_reason = spec["sentinel"], spec["low_base"]
    else:
        total_rate, total_reason = float(rate(total_num, total_den, spec["places"])), spec["ok"]

    book = Workbook()
    sheet = book.active
    sheet.title = spec["sheet"]
    sheet.append(spec["columns"])
    for segment in sorted(registered):
        cell = (float(rate(numerator[segment], denominator[segment], spec["places"]))
                if disposition[segment] == spec["ok"] else spec["sentinel"])
        sheet.append([segment, numerator[segment], denominator[segment], cell, disposition[segment]])
    sheet.append([spec["total"], total_num, total_den, total_rate, total_reason])
    book.save(ws / spec["workbook"])

    workings = spec["workings"]
    workings["period_start"], workings["period_end"] = start, end
    workings["rows_read"] = read
    workings["eligible_visits"] = sum(denominator.values())
    workings["excluded"] = {reason: excluded[reason] for reason in workings["excluded"]}
    workings["segments_published"] = len(published)
    workings["segments_suppressed"] = {
        code: sum(1 for s in registered if disposition[s] == code)
        for code in workings["segments_suppressed"]
    }
    workings["total_numerator"] = total_num
    workings["total_denominator"] = total_den
    workings["total_rate"] = total_rate
    (ws / spec["workings_file"]).write_text(
        json.dumps(workings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"read {read} rows, {sum(denominator.values())} eligible")
    print(f"published {len(published)} of {len(registered)} segments, total {total_rate}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
