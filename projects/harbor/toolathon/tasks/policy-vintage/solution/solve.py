"""policy-vintage: the decision register, derived from the published policies.

Every figure the decision turns on -- the receipt threshold, the subsistence
ceilings, the settlement rates, each version's identifier, status and effective
date -- is read out of the policy documents themselves, and the register's
columns are read out of Format_Example.xlsx, so a disagreement between the
workspace and the answer key fails the gate instead of being papered over.

The computation is the one the previous inline oracle ran; only the I/O boundary
moved. Reads arrive as values the manifest's tool calls bound, and the register
leaves as rows the manifest writes back through the excel server.

The manifest spells every read out as its own call. The documents in policy/ are
fixtures, so their paths are written there literally; the sheet names of
claims.xlsx and Format_Example.xlsx are not -- a solve step reads them out of
get_workbook_metadata and binds one per read call. Because the manifest's call
count is fixed and those names are discovered at run time, the two can disagree,
and `_group` and `_bind_sheets` below raise when they do rather than letting a
sheet go unread and the register be decided against less than the workspace holds.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: The cover line that marks a document as a version of the expense policy. The
#: accounts payable manual sits in the same folder and does not carry it, so it
#: is read and then passed over, exactly as the old walk passed over it.
COVER = "Document: Group Expense Policy"

#: The columns to fall back on when Format_Example.xlsx names none. The old
#: oracle carried the same fallback behind `if example.exists()`; the register
#: this task produces takes its header from the example workbook.
DEFAULT_HEADER = ["Claim", "Line", "VersionApplied", "Verdict", "Reason"]

#: How many calls the manifest carries for each group of reads. Every one of
#: these numbers is a count of steps in manifest.json, not a fact about the
#: answer: four documents published in policy/, one sheet read per workbook.
#: They exist so a mismatch is raised rather than quietly dropping a read.
POLICY_DOCUMENTS = 4
CLAIMS_SHEET_READS = 1
EXAMPLE_SHEET_READS = 1


class PolicyError(RuntimeError):
    """The workspace does not say what this solution needs it to say."""


# ------------------------------------------------------------------ tool payloads
def _group(bound: dict, prefix: str, expected: int) -> list:
    """The values bound as `prefix_00`, `prefix_01`, ..., in that order.

    `expected` is how many calls the manifest carries for the group. A missing
    binding means a read the manifest promised never landed; a stray one means a
    call binds a name nothing here consumes. Either way the register would be
    built from a different set of documents than the run actually read, so both
    raise instead of being absorbed.
    """
    wanted = [f"{prefix}_{i:02d}" for i in range(expected)]
    missing = [name for name in wanted if name not in bound]
    if missing:
        raise PolicyError(
            f"the manifest bound nothing under {missing}; it is expected to carry "
            f"{expected} {prefix} call(s)")
    stray = sorted(name for name in bound
                   if name.startswith(f"{prefix}_") and name not in wanted)
    if stray:
        raise PolicyError(
            f"{stray} were bound beyond the {expected} {prefix} call(s) this "
            f"solution reads; nothing would consume them")
    return [bound[name] for name in wanted]


def _docx(xml: str) -> tuple[list[str], list[list[list[str]]]]:
    """The paragraphs and tables of a .docx, from word-get_document_xml.

    Reproduces what python-docx handed the old oracle: `doc.paragraphs` text,
    and `doc.tables` as rows of `cell.text`, a cell's own paragraphs joined by
    newlines. These fixtures carry no merged cells and no nested tables. The XML
    declaration names an encoding, so parse the bytes.
    """
    def para_text(p) -> str:
        return "".join(node.text or "" for node in p.iter(f"{_W}t"))

    body = ElementTree.fromstring(xml.encode()).find(f"{_W}body")
    if body is None:
        raise PolicyError("a document came back from the word server with no body")

    paragraphs: list[str] = []
    tables: list[list[list[str]]] = []
    for child in body:
        if child.tag == f"{_W}p":
            paragraphs.append(para_text(child))
        elif child.tag == f"{_W}tbl":
            tables.append([
                ["\n".join(para_text(p) for p in cell.findall(f"{_W}p"))
                 for cell in row.findall(f"{_W}tc")]
                for row in child.findall(f"{_W}tr")
            ])
    return paragraphs, tables


def _grid(payload) -> list[list]:
    """read_data_from_excel returns one record per cell; rebuild the rectangle."""
    if not isinstance(payload, dict):
        return []
    cells = payload.get("cells") or []
    if not cells:
        return []
    top = min(c["row"] for c in cells)
    left = min(c["column"] for c in cells)
    grid = [[None] * (max(c["column"] for c in cells) - left + 1)
            for _ in range(max(c["row"] for c in cells) - top + 1)]
    for cell in cells:
        grid[cell["row"] - top][cell["column"] - left] = cell.get("value")
    return grid


def _sheet_names(meta, what: str) -> list[str]:
    sheets = (meta or {}).get("sheets") or []
    if not sheets:
        raise PolicyError(f"{what} reports no sheets: {meta!r}")
    return list(sheets)


def _bind_sheets(meta, what: str, prefix: str, reads: int) -> dict:
    """One binding per sheet -- `prefix_00`, `prefix_01`, ... -- for the reads.

    The manifest cannot name a sheet it has not read the metadata for, so each
    read takes its sheet name from here. It carries a fixed number of read calls
    while this number is discovered, so a workbook whose sheets have moved would
    leave a sheet unread or a call with nothing to reference. Raise loudly: a
    silently skipped sheet is a partially built register that still scores.
    """
    names = _sheet_names(meta, what)
    if len(names) != reads:
        raise PolicyError(
            f"{what} publishes {len(names)} sheet(s) {names!r}, but the manifest "
            f"carries {reads} read call(s) for it; the two have to agree")
    return {f"{prefix}_{i:02d}": name for i, name in enumerate(names)}


# ------------------------------------------------------------------ the policies
def as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    return date.fromisoformat(text) if text else None


def table_rows(tables: list[list[list[str]]], needle: str) -> dict[str, Decimal]:
    """The first table whose second heading names `needle`, as name -> figure.

    Each appendix carries more than one table -- the nightly accommodation
    ceiling sits beside the daily subsistence ceiling -- so the heading decides
    which one is read rather than its position.
    """
    for table in tables:
        if not table:
            continue
        header = [cell.strip() for cell in table[0]]
        if len(header) < 2 or needle.lower() not in header[1].lower():
            continue
        out: dict[str, Decimal] = {}
        for row in table[1:]:
            cells = [cell.strip() for cell in row]
            if len(cells) >= 2 and cells[0]:
                out[cells[0].strip().lower()] = Decimal(cells[1].replace(",", ""))
        return out
    return {}


def read_policy(xml: str) -> dict | None:
    """One published policy version, or None if the document is not one."""
    paragraphs, tables = _docx(xml)
    paragraphs = [p.strip() for p in paragraphs]
    if not any(p == COVER for p in paragraphs):
        return None
    body = "\n".join(paragraphs)

    version = re.search(r"^Version:\s*(\S+)\s*$", body, re.M)
    status = re.search(r"^Status:\s*(\S+)\s*$", body, re.M)
    effective = re.search(r"^Effective date:\s*(\d{4}-\d{2}-\d{2})\s*$", body, re.M)
    threshold = re.search(
        r"settled amount of that line\s+is\s+([\d.,]+)\s+or more", body)
    if not (version and status and effective and threshold):
        return None

    return {
        "version": version.group(1),
        "status": status.group(1).upper(),
        "effective": date.fromisoformat(effective.group(1)),
        "receipt_threshold": Decimal(threshold.group(1).replace(",", "")),
        "ceilings": table_rows(tables, "subsistence"),
        "rates": table_rows(tables, "settlement rate"),
    }


def load_policies(documents: list[str]) -> list[dict]:
    found = []
    for xml in documents:
        policy = read_policy(xml)
        if policy:
            found.append(policy)
    return found


def governing(policies: list[dict], when: date) -> dict | None:
    """The version in force on a date: APPROVED, latest effective date on or before it."""
    live = [p for p in policies
            if p["status"] == "APPROVED" and p["effective"] <= when]
    return max(live, key=lambda p: p["effective"]) if live else None


def settled(amount: Decimal, currency: str, policy: dict) -> Decimal:
    rate = policy["rates"].get(currency.strip().lower(), Decimal("1"))
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ceiling(destination: str, policy: dict) -> Decimal:
    table = policy["ceilings"]
    key = destination.strip().lower()
    if key in table:
        return table[key]
    for name, value in table.items():
        if "other" in name:
            return value
    raise PolicyError("no all-other-locations row in the subsistence appendix")


def output_header(payloads: list) -> list[str]:
    """The register's columns, as Format_Example.xlsx lays them out."""
    for payload in payloads:
        grid = _grid(payload)
        row = grid[0] if grid else None
        if row and any(c and "version" in str(c).lower() for c in row):
            return [str(c).strip() for c in row if c is not None]
    return list(DEFAULT_HEADER)


def claim_grid(payloads: list) -> list[list]:
    """The sheet of claims.xlsx carrying the open register, as a rectangle."""
    grids = [_grid(payload) for payload in payloads]
    for grid in grids:
        row = grid[0] if grid else None
        if row and "Claim" in [str(c).strip() for c in row if c is not None]:
            return grid
    if not grids:
        raise PolicyError("claims.xlsx published no sheets")
    return grids[0]


# ------------------------------------------------------------------ solve steps
def claims_sheets(bound: dict) -> dict:
    """The sheets of claims.xlsx; claim_grid picks the one carrying Claim."""
    return _bind_sheets(bound["claims_meta"], "claims.xlsx",
                        "claims_sheet", CLAIMS_SHEET_READS)


def example_sheets(bound: dict) -> dict:
    """The sheets of Format_Example.xlsx, one name per read call the manifest carries."""
    return _bind_sheets(bound["example_meta"], "Format_Example.xlsx",
                        "example_sheet", EXAMPLE_SHEET_READS)


def default_sheet(bound: dict) -> dict:
    """The sheet create_workbook left behind, so it can be renamed not added."""
    sheets = bound["out_meta"].get("sheets") or []
    if len(sheets) != 1:
        raise RuntimeError(f"a new workbook came back with sheets {sheets}")
    return {"out_default_sheet": sheets[0]}


def decide_claims(bound: dict) -> dict:
    """The decision register, from the values the manifest's reads brought back.

    Every document published in policy/ is read, the accounts payable manual
    among them; it does not carry the policy cover line, so `read_policy` passes
    over it. Withdrawn versions live outside that folder and are never opened:
    the manual's 6.2 puts them beyond force whatever date they name.
    """
    policies = load_policies(_group(bound, "policy_xml", POLICY_DOCUMENTS))
    if not policies:
        raise PolicyError("no expense policy documents found in the workspace")

    grid = claim_grid(_group(bound, "claims_cells", CLAIMS_SHEET_READS))
    if not grid:
        raise PolicyError("the claims sheet is empty")
    header = [str(c).strip() for c in grid[0]]
    records = [dict(zip(header, r)) for r in grid[1:]
               if r and any(c is not None for c in r)]

    decisions = []
    for rec in records:
        when = as_date(rec.get("ExpenseDate"))
        if when is None:
            decisions.append([rec["Claim"], rec["Line"],
                              "UNDETERMINED", "HOLD", "NO_EXPENSE_DATE"])
            continue

        policy = governing(policies, when)
        if policy is None:
            raise PolicyError(f"no approved policy in force on {when}")

        amount = settled(Decimal(str(rec["Amount"])), str(rec["Currency"]), policy)
        receipt = str(rec.get("Receipt") or "").strip().lower() == "yes"

        if amount >= policy["receipt_threshold"] and not receipt:
            verdict, reason = "REJECT", "NO_RECEIPT"
        elif amount <= ceiling(str(rec["Destination"]), policy):
            verdict, reason = "APPROVE", "WITHIN_CAP"
        else:
            verdict, reason = "REJECT", "OVER_CAP"

        decisions.append([rec["Claim"], rec["Line"], policy["version"], verdict, reason])

    rows = [output_header(_group(bound, "example_cells", EXAMPLE_SHEET_READS))]
    rows.extend(decisions)

    versions = ", ".join(f"{p['version']} ({p['status']}, {p['effective']})"
                         for p in policies)
    print(f"decided {len(decisions)} claim lines against {len(policies)} "
          f"policy versions: {versions}", file=sys.stderr)
    return {"rows": rows}
