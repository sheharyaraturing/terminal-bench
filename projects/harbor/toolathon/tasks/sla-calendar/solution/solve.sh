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
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------- read the SOP
def read_sop(path: Path) -> dict:
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paras)

    def need(pattern: str, flags: int = 0):
        m = re.search(pattern, text, flags)
        if not m:
            raise SystemExit(f"SOP does not state: {pattern}")
        return m

    spec: dict = {}
    spec["dead_queue"] = need(r"The\s+([A-Z][A-Z0-9-]*)\s+queue was decommissioned").group(1)

    hours = need(r"business hours are (\d{2}:\d{2}) to (\d{2}:\d{2}) local time")
    spec["open"] = hours.group(1)
    spec["close"] = hours.group(2)
    spec["half_close"] = need(r"marked HALF[^.]*?closes at (\d{2}:\d{2}) local time").group(1)

    bst_para = next(p for p in paras if "British Summer Time" in p)
    instants = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", bst_para)
    if len(instants) != 2:
        raise SystemExit("SOP does not pin the two clock-change instants")
    spec["bst_start"] = datetime.strptime(instants[0], UTC_FMT)
    spec["bst_end"] = datetime.strptime(instants[1], UTC_FMT)
    spec["bst_offset"] = timedelta(
        hours=int(need(r"British Summer Time, UTC\+(\d{2}):\d{2}").group(1))
    )

    spec["calendar"] = need(r"observes the ([A-Z]{2}(?:-[A-Z]{2,3})?) calendar only").group(1)
    spec["full_token"] = need(r"Type is (FULL) makes that date a non-working day").group(1)
    spec["half_token"] = need(r"Type is (HALF) leaves the date a working day").group(1)

    windows: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for table in doc.tables:
        head = [c.text.strip().lower() for c in table.rows[0].cells]
        if head[:1] == ["severity"]:
            for row in table.rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                windows[cells[0].upper()] = int(re.search(r"(\d+)\s*business hours", cells[1]).group(1))
        elif head[:1] == ["reason"]:
            for row in table.rows[1:]:
                code, when = (c.text.strip() for c in row.cells[:2])
                if "severity code" in when.lower():
                    reasons["severity"] = code
                elif "opened_utc is empty" in when.lower():
                    reasons["no_open"] = code
    if not windows or len(reasons) != 2:
        raise SystemExit("SOP is missing the response-window or exception-reason table")
    spec["windows"] = windows
    spec["reasons"] = reasons

    spec["default_window"] = int(
        need(r"default response window of (\d+) business hours").group(1)
    )
    spec["sentinel"] = need(r"write the single word ([A-Z]+) in both").group(1)

    fmt = need(r"in the format (\S+ \S+)\.").group(1)
    dpart, tpart = fmt.split()
    spec["deadline_fmt"] = (
        dpart.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
        + " "
        + tpart.replace("HH", "%H").replace("MM", "%M")
    )

    spec["report_name"] = need(r"Write (\S+\.xlsx) in the workspace root").group(1)
    spec["sheet"] = need(r"one sheet\s+named ([A-Za-z]+)").group(1)
    spec["columns"] = [
        c.strip()
        for c in need(r"header row must read ([^.]+?) in exactly that order").group(1).split(",")
    ]
    log = need(r"Write (\S+\.csv) in the workspace root with the header (\S+,\S+)")
    spec["log_name"] = log.group(1)
    spec["log_columns"] = [c.strip() for c in log.group(2).split(",")]
    yes_no = need(r"Breached is the word (\w+) or the word (\w+)")
    spec["yes"], spec["no"] = yes_no.group(1), yes_no.group(2)
    return spec


# ---------------------------------------------------------------- clock
class Clock:
    def __init__(self, spec: dict, full_days: set[date], half_days: set[date]) -> None:
        self.spec = spec
        self.full = full_days
        self.half = half_days
        self.open_h, self.open_m = (int(x) for x in spec["open"].split(":"))
        self.close_h, self.close_m = (int(x) for x in spec["close"].split(":"))
        self.half_h, self.half_m = (int(x) for x in spec["half_close"].split(":"))

    def to_local(self, u: datetime) -> datetime:
        return u + self.spec["bst_offset"] if self.spec["bst_start"] <= u < self.spec["bst_end"] else u

    def to_utc(self, local: datetime) -> datetime:
        lo = self.spec["bst_start"] + self.spec["bst_offset"]
        hi = self.spec["bst_end"] + self.spec["bst_offset"]
        return local - self.spec["bst_offset"] if lo <= local < hi else local

    def working(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.full

    def opens(self, d: date) -> datetime:
        return datetime(d.year, d.month, d.day, self.open_h, self.open_m)

    def closes(self, d: date) -> datetime:
        h, m = (self.half_h, self.half_m) if d in self.half else (self.close_h, self.close_m)
        return datetime(d.year, d.month, d.day, h, m)

    def next_working(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.working(d):
            d += timedelta(days=1)
        return d

    def start(self, local_open: datetime) -> datetime:
        d = local_open.date()
        if self.working(d):
            if local_open < self.opens(d):
                return self.opens(d)
            if local_open < self.closes(d):
                return local_open
        return self.opens(self.next_working(d))

    def deadline(self, local_open: datetime, hours: int) -> datetime:
        cur = self.start(local_open)
        left = timedelta(hours=hours)
        while True:
            avail = self.closes(cur.date()) - cur
            if left <= avail:
                return cur + left
            left -= avail
            cur = self.opens(self.next_working(cur.date()))


# ---------------------------------------------------------------- inputs
def read_calendar(path: Path, spec: dict) -> tuple[set[date], set[date]]:
    full: set[date] = set()
    half: set[date] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("Calendar") or "").strip() != spec["calendar"]:
                continue
            d = date.fromisoformat((row.get("Date") or "").strip())
            kind = (row.get("Type") or "").strip().upper()
            if kind == spec["full_token"]:
                full.add(d)
            elif kind == spec["half_token"]:
                half.add(d)
    return full, half


def read_as_of(path: Path) -> datetime:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return datetime.strptime(line, UTC_FMT)
    raise SystemExit("docs/as_of.txt carries no as-of instant")


def read_tickets(path: Path) -> list[dict]:
    rows = list(load_workbook(path, data_only=True).active.iter_rows(values_only=True))
    header = [str(c).strip() for c in rows[0]]
    out = []
    for row in rows[1:]:
        if row is None or all(c is None for c in row):
            continue
        out.append(dict(zip(header, row)))
    return out


def parse_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text, UTC_FMT)


# ---------------------------------------------------------------- solve
def solve(ws: Path) -> tuple[int, int]:
    spec = read_sop(ws / "sop" / "Support_SLA.docx")
    full, half = read_calendar(ws / "calendar" / "holidays_2026.csv", spec)
    clock = Clock(spec, full, half)
    as_of = read_as_of(ws / "docs" / "as_of.txt")
    tickets = read_tickets(ws / "tickets.xlsx")

    report: list[list[str]] = []
    log: list[list[str]] = []
    for t in tickets:
        if str(t.get("Queue") or "").strip() == spec["dead_queue"]:
            continue
        ref = str(t.get("Ticket") or "").strip()
        sev = str(t.get("Severity") or "").strip().upper()
        opened = parse_utc(t.get("Opened_UTC"))

        if sev not in spec["windows"]:
            log.append([ref, spec["reasons"]["severity"]])
        if opened is None:
            log.append([ref, spec["reasons"]["no_open"]])
            report.append([ref, sev, spec["sentinel"], spec["sentinel"]])
            continue

        hours = spec["windows"].get(sev, spec["default_window"])
        dl_local = clock.deadline(clock.to_local(opened), hours)
        dl_utc = clock.to_utc(dl_local)

        answered = parse_utc(t.get("FirstResponse_UTC"))
        late = (answered > dl_utc) if answered is not None else (as_of > dl_utc)
        report.append([ref, sev, dl_local.strftime(spec["deadline_fmt"]),
                       spec["yes"] if late else spec["no"]])

    report.sort(key=lambda r: r[0])
    log.sort(key=lambda r: (r[0], r[1]))

    wb = Workbook()
    sh = wb.active
    sh.title = spec["sheet"]
    sh.append(spec["columns"])
    for row in report:
        sh.append(row)
    wb.save(ws / spec["report_name"])

    with (ws / spec["log_name"]).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(spec["log_columns"])
        writer.writerows(log)
    return len(report), len(log)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    rows, exceptions = solve(ap.parse_args().workspace)
    print(f"reported {rows} tickets, logged {exceptions} exceptions")
PY

echo "Done!"
