#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
cd /workspace

uv run python - --workspace /app <<'PY'
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from docx import Document
from openpyxl import Workbook

CODE = re.compile(r"\d\.\d")

# ------------------------------------------------------------------ the rules
class Rules:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.required: dict[str, str] = {}
        self.gateway: set[str] = set()
        self.tests: dict[str, str] = {}
        self.placeholders: set[str] = set()
        self.reject_at = 0
        self.in_scope = "Submitted"
        self.sentinel_none = ""
        self.sentinel_flag = ""
        self.statuses: dict[str, str] = {}

def cells(row) -> list[str]:
    return [c.text.strip() for c in row.cells]

def read_rules(path: Path) -> Rules:
    doc = Document(path)
    r = Rules()

    for table in doc.tables:
        head = [c.lower() for c in cells(table.rows[0])]
        if head[:1] == ["item"] and "required" in head:
            i_item, i_req = head.index("item"), head.index("required")
            i_gate = head.index("gateway") if "gateway" in head else None
            for row in table.rows[1:]:
                c = cells(row)
                if not CODE.fullmatch(c[i_item]):
                    continue
                r.order.append(c[i_item])
                r.required[c[i_item]] = c[i_req]
                if i_gate is not None and c[i_gate].strip().upper() == "G":
                    r.gateway.add(c[i_item])
        elif head[:2] == ["item", "test"]:
            for row in table.rows[1:]:
                c = cells(row)
                if CODE.fullmatch(c[0]):
                    r.tests[c[0]] = c[1]

    text = "\n".join(p.text for p in doc.paragraphs)

    m = re.search(r"The tokens (.+?) are placeholders", text, re.S)
    if m:
        blob = m.group(1).replace(" and ", ", ")
        r.placeholders = {t.strip().lower() for t in blob.split(",") if t.strip()}

    m = re.search(r"\((\d+)\) or more items are\s+missing", text.replace("\n", " "))
    if not m:
        m = re.search(r"\((\d+)\) or more items are missing", text)
    r.reject_at = int(m.group(1))

    m = re.search(r"Status line reads (\w+)", text)
    r.in_scope = m.group(1)

    m = re.search(r"Write (\w+) when the form is Complete", text)
    r.sentinel_none = m.group(1)
    m = re.search(r"Write (\w+) when the form is Flag", text)
    r.sentinel_flag = m.group(1)

    m = re.search(r"Status is one of ([A-Za-z, ]+?)(?:, spelled|\.)", text)
    words = [w.strip() for w in m.group(1).replace(" or ", ", ").split(",") if w.strip()]
    r.statuses = {w.lower(): w for w in words}

    missing = [n for n, v in (("order", r.order), ("tests", r.tests),
                              ("placeholders", r.placeholders),
                              ("statuses", r.statuses)) if not v]
    if missing or not r.reject_at:
        raise SystemExit(f"could not read the checklist: {missing or 'reject threshold'}")
    return r

# ------------------------------------------------------------------ the forms
META = re.compile(r"^(FormID|Receipt|Submitted|Revision|Status)\s*:\s*(.*)$")
ITEM = re.compile(r"^(\d\.\d)\s+[^:]*:\s*(.*)$")

class Form:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.meta: dict[str, str] = {}
        self.values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            m = META.match(line.strip())
            if m:
                self.meta[m.group(1)] = m.group(2).strip()
                continue
            m = ITEM.match(line.strip())
            if m:
                self.values[m.group(1)] = m.group(2).strip()

    @property
    def form_id(self) -> str:
        return self.meta.get("FormID", "")

    @property
    def submitted(self) -> date:
        return date.fromisoformat(self.meta["Submitted"])

    @property
    def revision(self) -> int:
        try:
            return int(self.meta.get("Revision", "1"))
        except ValueError:
            return 1

# ------------------------------------------------------------------ evaluation
def parse_date(raw: str) -> date | None:
    if len(raw) != 10:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

def amount(raw: str) -> int | None:
    text = raw.replace("£", "").replace(",", "").replace(" ", "")
    if text.endswith(".00"):
        text = text[:-3]
    try:
        return int(text)
    except ValueError:
        return None

def answered(form: Form, code: str, rules: Rules) -> bool:
    raw = form.values.get(code, "").strip()
    return bool(raw) and raw.lower() not in rules.placeholders

def present(form: Form, code: str, rules: Rules) -> bool:
    if not answered(form, code, rules):
        return False
    raw = form.values[code].strip()
    test = rules.tests.get(code)
    if not test:
        return True

    m = re.fullmatch(r"digits\((\d+)-(\d+)\)", test)
    if m:
        return raw.isdigit() and int(m.group(1)) <= len(raw) <= int(m.group(2))

    m = re.fullmatch(r"enum\((.+)\)", test)
    if m:
        allowed = {v.strip().lower() for v in m.group(1).split(",")}
        return raw.lower() in allowed

    m = re.fullmatch(r"GBP (\d+)-(\d+)", test)
    if m:
        value = amount(raw)
        return value is not None and int(m.group(1)) <= value <= int(m.group(2))

    m = re.fullmatch(r"date (<=|>) Submitted", test)
    if m:
        d = parse_date(raw)
        if d is None:
            return False
        return d <= form.submitted if m.group(1) == "<=" else d > form.submitted

    raise SystemExit(f"unhandled value test {test!r}")

def gate_says(form: Form, code: str, rules: Rules) -> str | None:
    if not present(form, code, rules):
        return None
    return form.values[code].strip().lower()

def required(form: Form, code: str, rules: Rules) -> bool:
    rule = rules.required[code]
    if rule.strip().lower() == "always":
        return True

    m = re.fullmatch(r"If (\d\.\d)\s*=\s*(\w+)", rule.strip())
    if m:
        said = gate_says(form, m.group(1), rules)
        # C.3: an unevaluable condition leaves the items it gates required.
        return said is None or said == m.group(2).strip().lower()

    m = re.fullmatch(r"If (\d\.\d)\s*(>=|>|<=|<)\s*(\d+)", rule.strip())
    if m:
        trigger, op, bound = m.group(1), m.group(2), int(m.group(3))
        if not present(form, trigger, rules):
            return True
        value = amount(form.values[trigger].strip())
        if value is None:
            return True
        return {">=": value >= bound, ">": value > bound,
                "<=": value <= bound, "<": value < bound}[op]

    raise SystemExit(f"unhandled required rule {rule!r}")

def gated_by(rules: Rules) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for code, rule in rules.required.items():
        m = re.fullmatch(r"If (\d\.\d)\s*=\s*(\w+)", rule.strip())
        if m and m.group(2).strip().lower() == "yes":
            out.setdefault(m.group(1), []).append(code)
    return out

def triage(form: Form, rules: Rules) -> tuple[str, str]:
    for gate, items in gated_by(rules).items():
        if gate_says(form, gate, rules) == "no" and any(
                answered(form, c, rules) for c in items):
            return rules.statuses["flag"], rules.sentinel_flag

    missing = [c for c in rules.order
               if required(form, c, rules) and not present(form, c, rules)]
    if not missing:
        return rules.statuses["complete"], rules.sentinel_none
    if any(c in rules.gateway for c in missing) or len(missing) >= rules.reject_at:
        return rules.statuses["reject"], "; ".join(missing)
    return rules.statuses["fixable"], "; ".join(missing)

# ------------------------------------------------------------------ run
def solve(ws: Path) -> int:
    handbook = next(p for p in sorted((ws / "checklist").iterdir())
                    if p.suffix == ".docx")
    rules = read_rules(handbook)

    forms = [Form(p) for p in sorted((ws / "submissions").iterdir()) if p.is_file()]
    live = [f for f in forms
            if f.meta.get("Status", "").lower() == rules.in_scope.lower() and f.form_id]

    governing: dict[str, Form] = {}
    for f in live:
        held = governing.get(f.form_id)
        if held is None or (f.submitted, f.revision) > (held.submitted, held.revision):
            governing[f.form_id] = f

    book = Workbook()
    sheet = book.active
    sheet.title = "Triage"
    sheet.append(["FormID", "Status", "MissingItems"])
    for form_id in sorted(governing):
        status, items = triage(governing[form_id], rules)
        sheet.append([form_id, status, items])
    book.save(ws / "triage.xlsx")
    return len(governing)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, type=Path)
    print(f"triaged {solve(ap.parse_args().workspace)} forms")
PY

echo "Done!"
