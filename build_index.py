#!/usr/bin/env python3
"""Build a self-contained index.html to browse terminal-bench run artifacts.

Scans a runs/ directory (one subdirectory per run, named by run-id UUID) and
embeds every run's status.json, report.json, log.txt and harbor/* job files
into a single index.html you can open directly in a browser via file:// — no
server needed.

Usage:
    python3 build_index.py [runs_dir] [output_html]

Defaults:
    runs_dir   = ./runs
    output_html = ./runs/index.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# File extensions we treat as text (fetchable + shown verbatim). Everything
# else is listed by name/size only and marked binary in the UI.
# Largest a single text file's embedded payload may be. Bigger files are listed
# by name/size and flagged truncated in the UI so the HTML stays shareable.
MAX_FILE_BYTES = 0x40000  # 256 KiB

# Files whose contents we actually embed in the HTML. Only these are rendered
# (status/report drive the summary sections; check_report drives the rubric
# verdicts table). Everything else is listed by name/size only to keep the
# shared zip small.
EMBED_FILES = {"status.json", "report.json"}

TEXT_EXTS = {".json", ".log", ".txt", ".md", ".toml", ".yaml", ".yml", ".sh", ".py"}

# Files surfaced at the top of a run's file list, in priority order.
PRIORITY_FILES = ("status.json", "report.json", "log.txt")


def _read_text(path: Path) -> tuple[str, bool]:
    """Return (text, truncated). Reads up to MAX_FILE_BYTES as utf-8, replacing
    bad bytes; anything larger is truncated and flagged."""
    raw = path.read_bytes()[:MAX_FILE_BYTES]
    truncated = path.stat().st_size > MAX_FILE_BYTES
    return raw.decode("utf-8", errors="replace"), truncated


def _collect_run(run_dir: Path) -> dict:
    """Gather one run's file list AND embed the few files the page actually
    renders (status.json, report.json, any *check_report.json) so the resulting
    index.html is fully self-contained — openable via file:// with no server.

    status.json / report.json are parsed into run["status"] / run["report"] for
    the sidebar + summary sections. Other files are listed by name/size only.
    """
    run: dict = {"id": run_dir.name, "dir": str(run_dir), "files": []}

    status: dict | None = None
    report: dict | None = None

    seen: list[dict] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        ext = path.suffix.lower()
        ftype = "json" if ext == ".json" else ("text" if ext in TEXT_EXTS else "binary")
        entry: dict = {
            "path": rel,
            "name": path.name,
            "size": path.stat().st_size,
            "type": ftype,
        }
        embed = rel in EMBED_FILES or rel.endswith("check_report.json")
        if embed and ftype != "binary":
            text, truncated = _read_text(path)
            entry["content"] = text
            entry["truncated"] = truncated
            if rel == "status.json":
                try:
                    status = json.loads(text)
                except Exception:
                    status = {"_error": "status.json is not valid JSON"}
            elif rel == "report.json":
                try:
                    report = json.loads(text)
                except Exception:
                    report = {"_error": "report.json is not valid JSON"}
        else:
            entry["content"] = None
        seen.append(entry)

    def _sort_key(e: dict) -> tuple:
        p = e["path"]
        for i, name in enumerate(PRIORITY_FILES):
            if p == name:
                return (0, i)
        if p.endswith("check_report.json"):
            return (1, 0)
        if p.endswith("result.json"):
            return (2, 0)
        if p.endswith("job.log"):
            return (3, 0)
        return (4, p)

    seen.sort(key=_sort_key)
    run["files"] = seen
    run["status"] = status or {}
    run["report"] = report
    return run


def _collect_runs(runs_dir: Path) -> list[dict]:
    runs = []
    for child in sorted(runs_dir.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        if (child / "status.json").is_file() or (child / "harbor").is_dir():
            try:
                runs.append(_collect_run(child))
            except Exception as exc:
                runs.append({
                    "id": child.name,
                    "dir": str(child),
                    "files": [],
                    "_error": f"could not collect run: {exc}",
                })
    return runs


CSS = r"""
:root {
  --bg: #0d1117; --panel: #161b22; --panel2: #1c2230; --border: #30363d;
  --text: #e6edf3; --muted: #8b949e; --accent: #2f81f7; --code-bg: #0a0e14;
  --pass: #2ea043; --fail: #f85149; --skip: #d29922; --run: #a371f7;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  display: flex; height: 100vh; overflow: hidden;
}
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #484f58; }

#sidebar {
  width: 360px; min-width: 360px; background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; height: 100vh;
}
#sidebar header { padding: 16px; border-bottom: 1px solid var(--border); }
#sidebar header h1 { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
#sidebar header .sub { color: var(--muted); font-size: 12px; }
#filter { width: 100%; margin-top: 10px; padding: 8px 10px;
  background: var(--code-bg); color: var(--text); border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; }
#filter:focus { outline: none; border-color: var(--accent); }
#runlist { overflow-y: auto; flex: 1; }
.run-item { padding: 12px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; display: flex; flex-direction: column; gap: 4px; }
.run-item:hover { background: var(--panel2); }
.run-item.active { background: var(--panel2); border-left: 3px solid var(--accent); }
.run-item .rid { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
  color: var(--text); word-break: break-all; }
.run-item .rmeta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  font-size: 12px; color: var(--muted); }

#main { flex: 1; overflow-y: auto; }
#main .empty { color: var(--muted); padding: 40px; text-align: center; }
.section { padding: 20px 24px; border-bottom: 1px solid var(--border); }
.section h2 { margin: 0 0 12px; font-size: 15px; font-weight: 600; }
.section h3 { margin: 16px 0 8px; font-size: 13px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }

.runhead { padding: 20px 24px; border-bottom: 1px solid var(--border); }
.runhead h2 { margin: 0 0 8px; font-size: 16px; font-family: ui-monospace, monospace;
  word-break: break-all; }
.runhead .badges { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; border: 1px solid transparent; }
.badge-pass { background: rgba(46,160,67,.15); color: #56d364; border-color: rgba(46,160,67,.4); }
.badge-fail { background: rgba(248,81,73,.15); color: #ff7b72; border-color: rgba(248,81,73,.4); }
.badge-skip { background: rgba(210,153,34,.15); color: #e3b341; border-color: rgba(210,153,34,.4); }
.badge-run  { background: rgba(163,113,247,.15); color: #bc8cff; border-color: rgba(163,113,247,.4); }
.badge-muted { background: rgba(139,148,158,.12); color: var(--muted); border-color: var(--border); }

table.kv, table.checks { border-collapse: collapse; width: 100%; font-size: 13px; }
table.kv td, table.kv th { text-align: left; padding: 6px 10px;
  border-bottom: 1px solid var(--border); vertical-align: top; }
table.kv th { color: var(--muted); font-weight: 500; width: 200px; }
table.checks th, table.checks td { text-align: left; padding: 8px 10px;
  border-bottom: 1px solid var(--border); vertical-align: top; }
table.checks th { color: var(--muted); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; }
table.checks td.name { font-family: ui-monospace, monospace; white-space: nowrap; }
table.checks tr.fail td.name { color: #ff7b72; }
.check-output { white-space: pre-wrap; font-family: ui-monospace, monospace;
  font-size: 12px; color: var(--muted); max-height: 200px; overflow-y: auto;
  margin-top: 6px; background: var(--code-bg); padding: 8px 10px;
  border-radius: 6px; border: 1px solid var(--border); }

.file { border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; overflow: hidden; }
.file-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  background: var(--panel2); cursor: pointer; user-select: none; }
.file-head:hover { background: #222937; }
.file-head .chev { color: var(--muted); transition: transform .15s; font-size: 12px; }
.file.open .file-head .chev { transform: rotate(90deg); }
.file-head .fname { font-family: ui-monospace, monospace; font-size: 13px; }
.file-head .fsize { color: var(--muted); font-size: 12px; margin-left: auto; }
.file-head .ftype { color: var(--muted); font-size: 11px; }
.file-body { display: none; border-top: 1px solid var(--border); background: var(--code-bg); }
.file.open .file-body { display: block; }
pre.json, pre.text { margin: 0; padding: 14px 16px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12.5px;
  line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  max-height: 70vh; overflow: auto; color: #c9d1d9; }
.trunc-note { padding: 8px 16px; color: var(--skip); font-size: 12px;
  border-bottom: 1px solid var(--border); background: rgba(210,153,34,.08); }

.pill { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 11px;
  background: var(--panel2); border: 1px solid var(--border); color: var(--muted); }
a { color: var(--accent); }
.muted { color: var(--muted); }
.mono { font-family: ui-monospace, monospace; }
"""

JS = r"""
const runsById = Object.fromEntries(DATA.runs.map(r => [r.id, r]));
let activeId = null;

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}
function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function prettyJson(obj) {
  try { return JSON.stringify(obj, null, 2); } catch(e) { return String(obj); }
}
function fmtBytes(n) {
  if (n == null) return '';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0; while (n >= 1024 && i < u.length-1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(1)) + ' ' + u[i];
}
function badge(state) {
  if (!state) return '<span class="badge badge-muted">—</span>';
  const m = {passed:'badge-pass',failed:'badge-fail',skipped:'badge-skip',running:'badge-run'};
  const cls = m[state] || 'badge-muted';
  return '<span class="badge ' + cls + '">' + escapeHtml(state) + '</span>';
}
function fmtTime(s) {
  if (!s) return '—';
  return s.replace('T',' ').replace(/\+\d{2}:\d{2}$/, '');
}

function renderRunList(filter) {
  const list = document.getElementById('runlist');
  list.innerHTML = '';
  const f = (filter || '').toLowerCase();
  let shown = 0;
  for (const r of DATA.runs) {
    const st = r.status || {};
    const blob = (r.id + ' ' + (st.task_id||'') + ' ' + (st.state||'') + ' ' +
                 (st.project||'') + ' ' + (st.kind||'')).toLowerCase();
    if (f && !blob.includes(f)) continue;
    shown++;
    const item = el('div', 'run-item' + (r.id === activeId ? ' active' : ''));
    item.dataset.id = r.id;
    item.appendChild(el('div', 'rid', escapeHtml(r.id)));
    const meta = el('div', 'rmeta');
    meta.innerHTML = badge(st.state) +
      (st.task_id ? ' <span class="mono">' + escapeHtml(st.task_id) + '</span>' : '') +
      (st.project ? ' · ' + escapeHtml(st.project) : '');
    item.appendChild(meta);
    if (st.legs) {
      const legs = el('div', 'rmeta');
      for (const k of ['deterministic','rubric','validation']) {
        const lg = st.legs[k];
        if (lg) legs.innerHTML += badge(lg.state) + ' ';
      }
      item.appendChild(legs);
    }
    item.onclick = () => selectRun(r.id);
    list.appendChild(item);
  }
  document.getElementById('runcount').textContent =
    shown + (shown !== DATA.runs.length ? ' / ' + DATA.runs.length : '') + ' runs';
}

function selectRun(id) {
  activeId = id;
  renderRunList(document.getElementById('filter').value);
  renderRun(runsById[id]);
}

function kvRow(k, v) {
  return '<tr><th>' + escapeHtml(k) + '</th><td>' + (v == null ? '—' : v) + '</td></tr>';
}
function kvTable(obj) {
  if (!obj || typeof obj !== 'object') return '';
  let rows = '';
  for (const [k, v] of Object.entries(obj)) {
    let val;
    if (v == null) val = '—';
    else if (typeof v === 'object') val = '<pre class="json">' + escapeHtml(prettyJson(v)) + '</pre>';
    else val = escapeHtml(String(v));
    rows += '<tr><th>' + escapeHtml(k) + '</th><td>' + val + '</td></tr>';
  }
  return '<table class="kv">' + rows + '</table>';
}

function checksTable(checks, includeOutput) {
  if (!Array.isArray(checks) || !checks.length) return '<p class="muted">No checks.</p>';
  let body = '';
  for (const c of checks) {
    const cls = c.passed ? '' : 'fail';
    body += '<tr class="' + cls + '"><td class="name">' + escapeHtml(c.name || '') +
      '</td><td>' + (c.passed ? '<span class="badge badge-pass">pass</span>'
                              : '<span class="badge badge-fail">fail</span>') +
      '</td><td><span class="pill">' + escapeHtml(c.source || '') + '</span>';
    if (includeOutput && c.output) {
      body += '<div class="check-output">' + escapeHtml(c.output) + '</div>';
    }
    body += '</td></tr>';
  }
  return '<table class="checks"><thead><tr><th>Name</th><th>Result</th><th>Source / Output</th>' +
         '</tr></thead><tbody>' + body + '</tbody></table>';
}

function rubricTable(results) {
  // results is a list of {checks: {name: {explanation, outcome}}}
  if (!Array.isArray(results) || !results.length) return '<p class="muted">No rubric results.</p>';
  const checks = results[0] && results[0].checks;
  if (!checks) return '<p class="muted">No rubric checks found.</p>';
  const keys = Object.keys(checks);
  let body = '';
  for (const k of keys) {
    const c = checks[k];
    const outcome = (c.outcome || '').toLowerCase();
    const passed = outcome === 'pass' || outcome === 'not_applicable';
    const cls = passed ? '' : 'fail';
    const bcls = outcome === 'pass' ? 'badge-pass'
               : outcome === 'not_applicable' ? 'badge-skip' : 'badge-fail';
    body += '<tr class="' + cls + '"><td class="name">' + escapeHtml(k) +
      '</td><td><span class="badge ' + bcls + '">' + escapeHtml(outcome || '?') +
      '</span></td><td><div class="check-output">' +
      escapeHtml(c.explanation || '') + '</div></td></tr>';
  }
  return '<table class="checks"><thead><tr><th>Criterion</th><th>Verdict</th>' +
         '<th>Explanation</th></tr></thead><tbody>' + body + '</tbody></table>';
}

function fileBlock(f) {
  const head = el('div', 'file-head');
  head.innerHTML = '<span class="chev">▶</span>' +
    '<span class="fname">' + escapeHtml(f.path) + '</span>' +
    '<span class="ftype">' + escapeHtml(f.type) + '</span>' +
    '<span class="fsize">' + fmtBytes(f.size) + '</span>';
  const body = el('div', 'file-body');
  if (f.type === 'binary') {
    body.innerHTML = '<div class="trunc-note">Binary file - not inlined. ' +
      fmtBytes(f.size) + '</div>';
  } else {
    let inner = '';
    if (f.truncated) {
      inner += '<div class="trunc-note">Truncated at ' + fmtBytes(0x40000) +
        ' - full file is on disk.</div>';
    }
    let content = f.content || '';
    if (f.type === 'json') {
      try { content = JSON.stringify(JSON.parse(content), null, 2); }
      catch(e) { /* keep raw */ }
    }
    inner += '<pre class="' + (f.type === 'json' ? 'json' : 'text') + '">' +
      escapeHtml(content) + '</pre>';
    body.innerHTML = inner;
  }
  const block = el('div', 'file');
  block.appendChild(head);
  block.appendChild(body);
  head.onclick = () => block.classList.toggle('open');
  return block;
}

function renderRun(r) {
  const main = document.getElementById('main');
  main.innerHTML = '';
  const st = r.status || {};

  const head = el('div', 'runhead');
  head.innerHTML = '<h2>' + escapeHtml(r.id) + '</h2><div class="badges">' +
    badge(st.state) +
    (st.passed === true ? '<span class="badge badge-pass">passed</span>'
     : st.passed === false ? '<span class="badge badge-fail">not passed</span>' : '') +
    (st.task_id ? ' <span class="pill mono">' + escapeHtml(st.task_id) + '</span>' : '') +
    (st.project ? ' <span class="pill">' + escapeHtml(st.project) + '</span>' : '') +
    (st.kind ? ' <span class="pill">' + escapeHtml(st.kind) + '</span>' : '') +
    '</div>';
  main.appendChild(head);

  if (st._error) {
    const s = el('div', 'section');
    s.innerHTML = '<h2>Status error</h2><pre class="text">' + escapeHtml(st._error) + '</pre>';
    main.appendChild(s);
  } else {
    const s = el('div', 'section');
    s.innerHTML = '<h2>Status</h2>' + kvTable({
      run_id: st.run_id, project: st.project, project_type: st.project_type,
      kind: st.kind, task_id: st.task_id, state: st.state, passed: st.passed,
      created_at: fmtTime(st.created_at), started_at: fmtTime(st.started_at),
      finished_at: fmtTime(st.finished_at),
    });
    if (st.legs) {
      s.appendChild(el('h3', '', 'Legs'));
      let lrows = '';
      for (const [k, lg] of Object.entries(st.legs)) {
        lrows += '<tr><th>' + escapeHtml(k) + '</th><td>' + badge(lg.state) +
          ' <span class="muted">' + escapeHtml(lg.summary || '') + '</span></td></tr>';
      }
      s.innerHTML += '<table class="kv">' + lrows + '</table>';
    }
    main.appendChild(s);
  }

  // Deterministic + rubric + validation from report.json (embedded)
  if (r.report && !r.report._error) {
    const rep = r.report;
    const det = el('div', 'section');
    det.innerHTML = '<h2>Deterministic checks</h2>';
    if (rep.deterministic) {
      const summary = (rep.deterministic.passed ? 'passed' : 'failed') +
        ' · ' + (rep.deterministic.summary || '');
      det.innerHTML += '<p class="muted">' + escapeHtml(summary) + '</p>';
      det.innerHTML += checksTable(rep.deterministic.checks, true);
    } else {
      det.innerHTML += '<p class="muted">No deterministic section.</p>';
    }
    main.appendChild(det);

    const rub = el('div', 'section');
    rub.innerHTML = '<h2>LLM rubric review</h2>';
    if (rep.rubric) {
      rub.innerHTML += '<p class="muted">' +
        (rep.rubric.passed ? 'passed' : 'failed') + ' · ' +
        escapeHtml(rep.rubric.summary || '') + '</p>';
      if (rep.rubric.verdicts) {
        rub.innerHTML += checksTable(rep.rubric.verdicts.map(v => ({
          name: v.name, passed: v.verdict === 'pass' || v.verdict === 'not_applicable',
          source: v.verdict, output: v.reason,
        })), false);
      }
    } else {
      rub.innerHTML += '<p class="muted">No rubric section in report.json.</p>';
    }
    main.appendChild(rub);

    const val = el('div', 'section');
    val.innerHTML = '<h2>Validation</h2>';
    if (rep.validation) {
      val.innerHTML += '<p class="muted">' +
        (rep.validation.passed ? 'passed' : 'failed') + ' · ' +
        escapeHtml(rep.validation.summary || '') + '</p>';
      if (rep.validation.oracle_reward != null)
        val.innerHTML += '<p>oracle reward: <span class="mono">' +
          escapeHtml(rep.validation.oracle_reward) + '</span></p>';
      if (rep.validation.nop_reward != null)
        val.innerHTML += '<p>nop reward: <span class="mono">' +
          escapeHtml(rep.validation.nop_reward) + '</span></p>';
    } else {
      val.innerHTML += '<p class="muted">No validation section.</p>';
    }
    main.appendChild(val);
  } else if (r.report && r.report._error) {
    const s = el('div', 'section');
    s.innerHTML = '<h2>Report</h2><pre class="text">' + escapeHtml(r.report._error) + '</pre>';
    main.appendChild(s);
  }

  // Rubric verdicts from harbor check_report.json (rendered as a table)
  for (const f of r.files) {
    if (f.path.endsWith('check_report.json') && f.type === 'json') {
      try {
        const parsed = JSON.parse(f.content);
        if (parsed.results) {
          const rb = el('div', 'section');
          rb.innerHTML = '<h2>Rubric verdicts <span class="muted">(from ' +
            escapeHtml(f.path) + ')</span></h2>' + rubricTable(parsed.results);
          main.appendChild(rb);
          break;
        }
      } catch(e) {}
    }
  }
}

document.getElementById('filter').addEventListener('input', e =>
  renderRunList(e.target.value));
renderRunList('');
if (DATA.runs.length) selectRun(DATA.runs[0].id);
"""


def build_html(runs: list[dict], runs_dir: Path) -> str:
    payload = json.dumps({"runs": runs}, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>terminal-bench runs</title>
<style>
{CSS}
</style>
</head>
<body>
<div id="sidebar">
  <header>
    <h1>terminal-bench runs</h1>
    <div class="sub" id="runcount">—</div>
    <input id="filter" placeholder="Filter by run id, task, state…" />
  </header>
  <div id="runlist"></div>
</div>
<div id="main"><div class="empty">Select a run on the left.</div></div>
<script>
const DATA = {payload};
{JS}
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    runs_dir = Path(argv[1]) if len(argv) > 1 else Path("runs")
    out_html = Path(argv[2]) if len(argv) > 2 else runs_dir / "index.html"

    if not runs_dir.is_dir():
        print(f"error: runs dir not found: {runs_dir}", file=sys.stderr)
        return 1

    runs = _collect_runs(runs_dir)
    html = build_html(runs, runs_dir)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    total_files = sum(len(r["files"]) for r in runs)
    print(f"wrote {out_html} — {len(runs)} runs, {total_files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
