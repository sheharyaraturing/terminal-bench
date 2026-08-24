#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from docx import Document
from openpyxl import Workbook, load_workbook

REQ_COLUMNS = ["Ref", "Requester", "CostCentre", "Vendor", "Amount", "Raised", "Status"]
LINK_DAYS = 7


class PolicyError(RuntimeError):
    """The manual does not say what this solution needs it to say."""


def _need(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        raise PolicyError(f"could not find {what} in the Finance Manual")
    return m


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip()[:10])


# --------------------------------------------------------------------------- period


def read_period(path: Path) -> tuple[date, date]:
    text = path.read_text(encoding="utf-8")
    start = _need(r"Period start\s*:\s*(\d{4}-\d{2}-\d{2})", text, "the period start date")
    end = _need(r"Period end\s*:\s*(\d{4}-\d{2}-\d{2})", text, "the period end date")
    return date.fromisoformat(start.group(1)), date.fromisoformat(end.group(1))


# --------------------------------------------------------------------------- policy


class Policy:
    def __init__(self, path: Path):
        doc = Document(path)
        self.text = "\n".join(p.text for p in doc.paragraphs)

        self.levels, self.lower = self._read_bands(doc)
        self.matrix = self._read_matrix(doc)

        m = _need(r"[Oo]nly requisitions with a status of ([a-z-]+) or ([a-z-]+) are routed",
                  self.text, "the routable statuses")
        self.routable = (m.group(1), m.group(2))

        m = _need(r"cost centre does not appear in this table is approved by the "
                  r"([A-Za-z][A-Za-z ]*?) of ([A-Z]{2}-\d{3})",
                  self.text, "the rule for a cost centre outside the matrix")
        self.fallback_level, self.fallback_cc = m.group(1).strip(), m.group(2)

        m = _need(r"Cost centre ([A-Z]{2}-\d{3}) operates under a research delegation",
                  self.text, "the cost centre that has a research delegation")
        self.delegate_cc = m.group(1)
        m = _need(r"research delegate, ([^,]+),", self.text, "the name of the research delegate")
        self.delegate = m.group(1).strip()

        m = _need(r"designates the requester at the ([A-Za-z][A-Za-z ]*?) band there is no level "
                  r"above, and approval passes to the ([A-Za-z][A-Za-z ]*?)\.",
                  self.text, "the remedy for self-approval at the top band")
        self.top_band, self.board = m.group(1).strip(), m.group(2).strip()

        m = _need(r"that fallback approver is the requester, approval passes to the "
                  r"([A-Za-z][A-Za-z ]*?) of ([A-Z]{2}-\d{3})",
                  self.text, "the remedy for self-approval under the fallback")
        self.fallback_escalation_level, self.fallback_escalation_cc = m.group(1).strip(), m.group(2)

        m = _need(r"routing log records ([A-Z]+) in place of an approver",
                  self.text, "the marker used for a requisition with no cost centre")
        self.hold = m.group(1)

        _need(r"linkage carries", self.text, "the statement that 7.6 linkage carries along a chain")
        _need(r"group is formed on requester and supplier alone", self.text,
              "the statement of the 7.6 grouping key")
        _need(r"up to, but not including, the lower bound of the band above",
              self.text, "the statement that bands are half-open")

        if self.top_band != self.levels[-1]:
            raise PolicyError(f"7.6 names {self.top_band!r} as the top band, 7.4 lists {self.levels[-1]!r}")

    # -- tables ------------------------------------------------------------

    def _read_bands(self, doc) -> tuple[list[str], dict[str, float]]:
        for table in doc.tables:
            header = [c.text.strip() for c in table.rows[0].cells]
            if not header or header[0].lower() != "cost centre":
                continue
            parsed = []
            for cell in header[1:]:
                m = re.match(r"(.+?)\s*\(\s*([\d,]+)", cell)
                if not m:
                    parsed = []
                    break
                parsed.append((m.group(1).strip(), _num(m.group(2))))
            if len(parsed) < 2:
                continue
            parsed.sort(key=lambda x: x[1])
            if parsed[0][1] != 0:
                raise PolicyError(f"the lowest band starts at {parsed[0][1]}, not 0")
            return [n for n, _ in parsed], {n: lo for n, lo in parsed}
        raise PolicyError("no operating-expenditure band table found")

    def _read_matrix(self, doc) -> dict[str, dict[str, str]]:
        for table in doc.tables:
            header = [c.text.strip() for c in table.rows[0].cells]
            if not header or header[0].lower() != "cost centre":
                continue
            names = []
            for cell in header[1:]:
                m = re.match(r"(.+?)\s*\(", cell)
                if not m:
                    names = []
                    break
                names.append(m.group(1).strip())
            if names != self.levels and sorted(names) != sorted(self.levels):
                continue
            matrix = {}
            for row in table.rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                matrix[cells[0]] = dict(zip(names, cells[1:]))
            return matrix
        raise PolicyError("no operating-expenditure approval matrix found")

    # -- rules -------------------------------------------------------------

    def band_for(self, amount: float) -> str:
        """A band runs from its lower bound up to the next band's lower bound."""
        for level in reversed(self.levels):
            if amount >= self.lower[level]:
                return level
        raise PolicyError(f"amount {amount!r} sits below every band in 7.4")

    def approver_for(self, cost_centre: str, band: str, requester: str) -> str:
        cc = (cost_centre or "").strip()
        if not cc:
            return self.hold                                          # 7.3

        listed = cc in self.matrix
        approver = self.matrix[cc][band] if listed \
            else self.matrix[self.fallback_cc][self.fallback_level]   # 7.4

        if approver != requester:                                     # 7.6
            return approver

        if not listed:
            escalated = self.matrix[self.fallback_escalation_cc][self.fallback_escalation_level]
        elif cc == self.delegate_cc:
            escalated = self.delegate
        elif band == self.levels[-1]:
            escalated = self.board
        else:
            escalated = self.matrix[cc][self.levels[self.levels.index(band) + 1]]

        if escalated == requester:
            raise PolicyError(f"escalation from {band} in {cc} still designates {requester}")
        return escalated


# --------------------------------------------------------------------------- workbook io


def read_requisitions(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        if not set(REQ_COLUMNS) <= set(header):
            continue
        idx = {c: header.index(c) for c in REQ_COLUMNS}
        out = []
        for r in rows[1:]:
            if r is None or all(c is None for c in r):
                continue
            rec = {c: r[idx[c]] for c in REQ_COLUMNS}
            rec["Ref"] = str(rec["Ref"]).strip()
            rec["CostCentre"] = "" if rec["CostCentre"] is None else str(rec["CostCentre"]).strip()
            rec["Status"] = str(rec["Status"]).strip().lower()
            rec["Amount"] = float(rec["Amount"])
            rec["Raised"] = _as_date(rec["Raised"])
            out.append(rec)
        return out
    raise RuntimeError(f"no sheet in {path.name} carries the columns {REQ_COLUMNS}")


def group_key(records: list[dict]) -> dict[str, list[dict]]:
    """7.6: same requester and supplier, linked by gaps of <= 7 days, linkage carries."""
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        by_pair.setdefault((r["Requester"], r["Vendor"]), []).append(r)

    groups: dict[str, list[dict]] = {}
    for members in by_pair.values():
        members.sort(key=lambda r: r["Raised"])
        cluster = [members[0]]
        for prev, nxt in zip(members, members[1:]):
            if (nxt["Raised"] - prev["Raised"]).days <= LINK_DAYS:
                cluster.append(nxt)
            else:
                for m in cluster:
                    groups[m["Ref"]] = cluster
                cluster = [nxt]
        for m in cluster:
            groups[m["Ref"]] = cluster
    return groups


def solve(ws: Path) -> int:
    start, end = read_period(ws / "period.txt")
    policy = Policy(ws / "policy/Finance_Manual.docx")
    records = read_requisitions(ws / "requisitions.xlsx")

    scope = [r for r in records
             if r["Status"] in policy.routable and start <= r["Raised"] <= end]
    groups = group_key(scope)

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Routing"
    sheet.append(["Ref", "Approver", "Band"])

    routed = 0
    for r in records:
        if r["Ref"] not in groups:
            continue
        combined = sum(m["Amount"] for m in groups[r["Ref"]])
        band = policy.band_for(combined)
        sheet.append([r["Ref"], policy.approver_for(r["CostCentre"], band, r["Requester"]), band])
        routed += 1

    wb.save(ws / "routing_log.xlsx")
    print(f"routed {routed} of {len(records)} requisitions for {start} to {end}")
    return routed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    solve(ap.parse_args().workspace)
PY

echo "Done!"
