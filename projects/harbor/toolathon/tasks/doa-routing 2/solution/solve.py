"""doa-routing, derived through the task's own tool surface.

The Finance Manual is the authority and every rule is read out of it. The
MANIFEST below names what to read and what to write; the generated runner owns
the gateway session and the multi-call dances behind each kind, so derive() is
ordinary Python over values that arrived through tool calls.

A passing run proves the workspace is reachable and the answer expressible
through the gateway tools this script calls. It does NOT prove the surface is
workable for a model: the host loop hands the model
`result.content[0].model_dump_json()` and never inspects isError, so a model
unwraps an envelope and detects failure by reading text, where this script
reads `part.text` and raises on isError.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime


REQ_COLUMNS = ["Ref", "Requester", "CostCentre", "Vendor", "Amount", "Raised", "Status"]
LINK_DAYS = 7

#: A cost-centre code, e.g. RD-200. Marks where a matrix header stops and its
#: body begins once `get_document_text` has flattened the table.
CC_CODE = re.compile(r"^[A-Z]{2}-\d{3}$")


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


def read_period(text: str) -> tuple[date, date]:
    start = _need(r"Period start\s*:\s*(\d{4}-\d{2}-\d{2})", text, "the period start date")
    end = _need(r"Period end\s*:\s*(\d{4}-\d{2}-\d{2})", text, "the period end date")
    return date.fromisoformat(start.group(1)), date.fromisoformat(end.group(1))


# --------------------------------------------------------------------------- policy


def _cost_centre_tables(text: str) -> list[list[list[str]]]:
    """Recover the manual's delegation tables from flattened document text.

    The word server returns paragraphs first and then every table appended one
    cell per line in row-major order, with no row or table boundaries. Both
    tables this solution needs open with a `Cost centre` corner cell — which is
    also the only kind of table the derivation ever looks at — so each anchor
    starts a table, its header runs until the first cost-centre code, and that
    header's length gives the row width for the body.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    anchors = [i for i, ln in enumerate(lines) if ln.lower() == "cost centre"]
    tables = []
    for pos, start in enumerate(anchors):
        stop = anchors[pos + 1] if pos + 1 < len(anchors) else len(lines)
        cells = lines[start:stop]
        width = next(
            (i for i, cell in enumerate(cells) if i and CC_CODE.match(cell)),
            0,
        )
        if width < 2 or (len(cells) - width) % width:
            continue
        tables.append([cells[i : i + width] for i in range(0, len(cells), width)])
    return tables


class Policy:
    def __init__(self, text: str):
        self.text = text
        tables = _cost_centre_tables(text)

        self.levels, self.lower = self._read_bands(tables)
        self.matrix = self._read_matrix(tables)

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

    def _read_bands(self, tables) -> tuple[list[str], dict[str, float]]:
        for table in tables:
            parsed = []
            for cell in table[0][1:]:
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

    def _read_matrix(self, tables) -> dict[str, dict[str, str]]:
        for table in tables:
            names = []
            for cell in table[0][1:]:
                m = re.match(r"(.+?)\s*\(", cell)
                if not m:
                    names = []
                    break
                names.append(m.group(1).strip())
            if names != self.levels and sorted(names) != sorted(self.levels):
                continue
            return {row[0]: dict(zip(names, row[1:])) for row in table[1:]}
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


def records_from_grid(grid: list[list]) -> list[dict] | None:
    """The requisitions, if this sheet is the one carrying them."""
    if not grid:
        return None
    header = [str(c).strip() if c is not None else "" for c in grid[0]]
    if not set(REQ_COLUMNS) <= set(header):
        return None
    idx = {c: header.index(c) for c in REQ_COLUMNS}
    out = []
    for r in grid[1:]:
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

def requisitions_range(bound: dict) -> dict:
    """The last cell of the requisitions sheet, for the read that follows."""
    used = (bound["req_meta"].get("used_ranges") or {}).get("Requisitions")
    if not used or ":" not in used:
        raise RuntimeError(f"requisitions.xlsx reports no used range: {used!r}")
    return {"req_end": used.split(":")[-1]}


def default_sheet(bound: dict) -> dict:
    """The sheet create_workbook left behind, so it can be renamed not added."""
    sheets = bound["out_meta"].get("sheets") or []
    if len(sheets) != 1:
        raise RuntimeError(f"a new workbook came back with sheets {sheets}")
    return {"out_default_sheet": sheets[0]}


def _grid(payload: dict) -> list[list]:
    """read_data_from_excel returns one record per cell; rebuild the rectangle."""
    cells = payload["cells"]
    if not cells:
        return []
    top = min(c["row"] for c in cells)
    left = min(c["column"] for c in cells)
    grid = [[None] * (max(c["column"] for c in cells) - left + 1)
            for _ in range(max(c["row"] for c in cells) - top + 1)]
    for cell in cells:
        grid[cell["row"] - top][cell["column"] - left] = cell.get("value")
    return grid


def route_requisitions(inputs: dict) -> dict:
    """The routing log, from the values the manifest's reads brought back."""
    start, end = read_period(inputs["period"])
    policy = Policy(inputs["manual"])

    records = records_from_grid(_grid(inputs["req_cells"]))
    if records is None:
        raise RuntimeError(f"the requisitions sheet does not carry {REQ_COLUMNS}")

    scope = [r for r in records
             if r["Status"] in policy.routable and start <= r["Raised"] <= end]
    groups = group_key(scope)

    rows = [["Ref", "Approver", "Band"]]
    for r in records:
        if r["Ref"] not in groups:
            continue
        combined = sum(m["Amount"] for m in groups[r["Ref"]])
        band = policy.band_for(combined)
        rows.append([r["Ref"], policy.approver_for(r["CostCentre"], band, r["Requester"]), band])

    print(f"routed {len(rows) - 1} of {len(records)} requisitions for {start} to {end}",
          file=sys.stderr)
    return {"rows": rows}
