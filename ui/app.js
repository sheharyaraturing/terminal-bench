/* Autoreviewer UI. No build step: plain DOM, fetch, polling. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.flat().forEach((k) => n.append(k?.nodeType ? k : document.createTextNode(k ?? "")));
  return n;
};
const badge = (text, cls) => el("span", { className: `badge ${cls ?? text}` }, text);

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? res.statusText));
  }
  return body;
}

/* ── tabs ───────────────────────────────────────────────────────────────── */
$$(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "trainer") { loadTrainerProjects(); loadRuns(); syncRunListTimer(); loadDockerState(); }
  })
);

/* ── delivery manager: create ───────────────────────────────────────────── */
const TYPE_HINTS = {
  harbor: "Harbor: your uploaded checks run in addition to the common terminal-bench set.",
  "non-harbor": "Non-Harbor: only the checks you upload here will run.",
};
function syncTypeHint() { $("#type-hint").textContent = TYPE_HINTS[$("#create-type").value]; }
$("#create-type").addEventListener("change", syncTypeHint);
syncTypeHint();

$("#create-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const out = $("#create-result");
  out.className = "result";
  out.textContent = "Creating…";
  const fd = new FormData();
  fd.append("name", form.name.value.trim());
  fd.append("type", form.type.value);
  fd.append("description", form.description.value);
  if (form.validation_mode.value) fd.append("validation_mode", form.validation_mode.value);
  if (form.rubric_text.value.trim()) fd.append("rubric_text", form.rubric_text.value);
  if (form.rubric_file.files[0]) fd.append("rubric_file", form.rubric_file.files[0]);
  for (const f of form.checks.files) fd.append("checks", f);
  for (const f of form.extra_references.files) fd.append("extra_references", f);
  try {
    const p = await api("/api/projects", { method: "POST", body: fd });
    out.className = "result ok";
    out.textContent = `Created ${p.name} (${p.type}) — ${p.project_checks} project check(s), ${p.common_checks} common, ${p.rubric_criteria.length} rubric criteria.`;
    form.reset();
    syncTypeHint();
    await loadProjects();
    await showProject(p.name);
  } catch (e) {
    out.className = "result err";
    out.textContent = `Error: ${e.message}`;
  }
});

/* ── delivery manager: project list + detail ────────────────────────────── */
let selectedProject = null;

async function loadProjects() {
  const list = $("#project-list");
  list.replaceChildren();
  const projects = await api("/api/projects");
  if (!projects.length) list.append(el("li", {}, el("span", { className: "muted" }, "No projects yet.")));
  for (const p of projects) {
    list.append(el("li", { className: p.name === selectedProject ? "selected" : "" },
      el("span", { className: "name", onclick: () => showProject(p.name) }, p.name),
      badge(p.type, p.type),
      el("span", { className: "muted" }, `${p.tasks} tasks · ${p.project_checks + p.common_checks} checks`)
    ));
  }
}

async function showProject(name) {
  selectedProject = name;
  await loadProjects();
  const box = $("#project-detail");
  box.replaceChildren(el("p", { className: "muted" }, "Loading…"));
  const p = await api(`/api/projects/${encodeURIComponent(name)}`);
  const rubricLine = p.has_rubric ? `${p.rubric_path} — ${p.rubric_criteria.length} criteria` : "no rubric yet";
  box.replaceChildren(
    el("h3", {}, "Detail"),
    el("p", { className: "kv" }, `${p.type} · validation: ${p.validation_mode} · ${p.description || "no description"}`),
    el("p", { className: "kv" }, `Rubric: ${rubricLine}`),
    p.rubric_criteria.length ? el("ul", { className: "list" }, p.rubric_criteria.map((c) => el("li", {}, el("span", {}, c)))) : el("span"),
    el("h3", {}, "Project checks"), checksList(p),
    el("form", { id: "add-check-form" },
      el("label", {}, "Add checks (.sh / .py)", el("input", { type: "file", name: "files", multiple: true, accept: ".sh,.py" })),
      el("button", { type: "submit", className: "ghost" }, "Upload checks")),
    el("div", { id: "check-result", className: "result" }),
    p.common_check_names.length
      ? el("details", {},
          el("summary", {}, `Inherited common checks (${p.common_check_names.length})`),
          el("p", { className: "readonly" }, "From the repo-root checks/ set — read-only here. A project check with the same filename overrides one."),
          el("ul", { className: "list" }, p.common_check_names.map((c) => el("li", {}, el("span", {}, c), badge("common", "skip")))))
      : el("p", { className: "muted" }, "This project runs only its own checks."),
    el("h3", {}, "Rubric source"), el("pre", { id: "rubric-src" }, p.has_rubric ? "" : "(none)")
  );
  if (p.has_rubric) api(`/api/projects/${encodeURIComponent(name)}/rubric`).then((r) => { $("#rubric-src").textContent = r.content; }).catch(() => {});
  $("#add-check-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = ev.target.querySelector("input[type=file]");
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("files", f);
    const out = $("#check-result");
    try {
      const r = await api(`/api/projects/${encodeURIComponent(name)}/checks`, { method: "POST", body: fd });
      out.className = "result ok"; out.textContent = `Uploaded: ${r.written.join(", ")}`;
      await showProject(name);
    } catch (e) { out.className = "result err"; out.textContent = `Error: ${e.message}`; }
  });
}

function checksList(p) {
  if (!p.project_check_names.length) return el("p", { className: "muted" }, "No project-specific checks uploaded.");
  return el("ul", { className: "list" }, p.project_check_names.map((c) =>
    el("li", {}, el("span", {}, c),
      el("button", { className: "ghost tiny", onclick: async () => {
        await api(`/api/projects/${encodeURIComponent(p.name)}/checks/${encodeURIComponent(c)}`, { method: "DELETE" });
        showProject(p.name);
      }}, "Delete"))
  ));
}
$("#refresh-projects").addEventListener("click", loadProjects);

/* ── trainer: projects + tasks ──────────────────────────────────────────── */
let trainerProjects = [];

async function loadTrainerProjects() {
  trainerProjects = await api("/api/projects");
  const sel = $("#trainer-project");
  const previous = sel.value;
  sel.replaceChildren(...trainerProjects.map((p) => el("option", { value: p.name }, `${p.name} (${p.type})`)));
  if (trainerProjects.some((p) => p.name === previous)) sel.value = previous;
  const fsel = $("#run-filter-project");
  const fprev = fsel.value;
  fsel.replaceChildren(el("option", { value: "" }, "all projects"), ...trainerProjects.map((p) => el("option", { value: p.name }, p.name)));
  if (trainerProjects.some((p) => p.name === fprev)) fsel.value = fprev;
  // Trajectory analysis project picker
  const tsel = $("#traj-project");
  const tprev = tsel.value;
  tsel.replaceChildren(...trainerProjects.map((p) => el("option", { value: p.name }, `${p.name} (${p.type})`)));
  if (trainerProjects.some((p) => p.name === tprev)) tsel.value = tprev;
  syncTrainerHint();
  syncTrajHint();
  await loadTasks();
  await loadTrajTasks();
  await loadTrajJobs();
}

function currentProject() { return trainerProjects.find((p) => p.name === $("#trainer-project").value); }
function syncTrainerHint() {
  const p = currentProject();
  $("#trainer-hint").textContent = p
    ? `${p.type} · ${p.project_checks} project check(s) + ${p.common_checks} common · rubric ${p.has_rubric ? "present" : "MISSING"}`
    : "No projects yet — create one in the Delivery Manager tab.";
}
$("#trainer-project").addEventListener("change", () => { syncTrainerHint(); loadTasks(); });

function currentTrajProject() { return trainerProjects.find((p) => p.name === $("#traj-project").value); }
function syncTrajHint() {
  const p = currentTrajProject();
  $("#traj-hint").textContent = p
    ? `${p.type} · ${p.tasks} task(s) available · rubric ${p.has_rubric ? "present" : "MISSING"}`
    : "No projects yet — create one in the Delivery Manager tab.";
}
$("#traj-project").addEventListener("change", () => { syncTrajHint(); loadTrajTasks(); loadTrajJobs(); });

async function loadTrajTasks() {
  const sel = $("#traj-task");
  const prev = sel.value;
  sel.replaceChildren(el("option", { value: "" }, "(none — trajectories only)"));
  const p = currentTrajProject();
  if (!p) return;
  try {
    const { tasks } = await api(`/api/projects/${encodeURIComponent(p.name)}/tasks`);
    for (const t of tasks) sel.append(el("option", { value: t }, t));
    if (tasks.some((t) => t === prev)) sel.value = prev;
  } catch { /* leave the none option */ }
}

async function loadTasks() {
  const list = $("#task-list");
  list.replaceChildren();
  const p = currentProject();
  if (!p) return;
  const { tasks } = await api(`/api/projects/${encodeURIComponent(p.name)}/tasks`);
  if (!tasks.length) { list.append(el("li", {}, el("span", { className: "muted" }, "No tasks uploaded yet."))); return; }
  for (const t of tasks) {
    list.append(el("li", {},
      el("span", { className: "name", title: t }, t),
      el("button", { className: "primary tiny", onclick: () => runTask(p.name, t) }, "Run review"),
      el("button", { className: "ghost tiny", onclick: async () => {
        if (!confirm(`Delete task ${t}? This removes it from disk.`)) return;
        await api(`/api/projects/${encodeURIComponent(p.name)}/tasks/${encodeURIComponent(t)}`, { method: "DELETE" });
        loadTasks();
      }}, "Delete")
    ));
  }
}

$("#task-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const p = currentProject();
  const out = $("#task-result");
  if (!p) { out.className = "result err"; out.textContent = "Pick a project first."; return; }
  const file = $("#task-file").files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const tid = ev.target.task_id.value.trim();
  if (tid) fd.append("task_id", tid);
  out.className = "result"; out.textContent = "Uploading…";
  try {
    const r = await api(`/api/projects/${encodeURIComponent(p.name)}/tasks`, { method: "POST", body: fd });
    out.className = "result ok";
    out.textContent = `Uploaded ${r.task_id} (${r.kind})${r.contents ? ` — ${r.contents.join(", ")}` : ""}`;
    ev.target.reset();
    await loadTasks();
  } catch (e) { out.className = "result err"; out.textContent = `Error: ${e.message}`; }
});

/* ── trainer: analyze trajectories ──────────────────────────────────────── */
let trajTree = null;             // {folders:[{name, runs:[{name,path}]}]}
const trajSelected = new Set();  // selected trial-dir paths

function currentTrajProjectName() { return $("#traj-project").value; }

async function loadTrajJobs() {
  resetTrajTree();
  const name = currentTrajProjectName();
  if (!name) return;
  try {
    const r = await api(`/api/projects/${encodeURIComponent(name)}/jobs`);
    setTrajTree(r.tree);
  } catch { resetTrajTree(); }
}

function resetTrajTree() {
  trajTree = null; trajSelected.clear();
  $("#traj-tree-wrap").hidden = true;
  $("#traj-empty").hidden = true;
  $("#traj-tree").replaceChildren();
  syncTrajSubmit();
}

function syncTrajSubmit() {
  const count = trajSelected.size;
  $("#traj-selected-count").textContent = trajTree ? `${count} run(s) selected` : "";
  $("#traj-submit").disabled = !trajTree || count === 0;
}

function setTrajTree(tree) {
  trajTree = tree; trajSelected.clear();
  const folders = tree.folders || [];
  if (!folders.length) { $("#traj-tree-wrap").hidden = true; $("#traj-empty").hidden = false; syncTrajSubmit(); return; }
  for (const f of folders) for (const run of f.runs || []) trajSelected.add(run.path);
  $("#traj-empty").hidden = true;
  renderTrajTree();
}

function renderTrajTree() {
  const box = $("#traj-tree");
  box.replaceChildren();
  if (!trajTree) { syncTrajSubmit(); return; }
  for (const folder of trajTree.folders || []) {
    const runs = folder.runs || [];
    const folderCb = el("input", { type: "checkbox" });
    folderCb.checked = runs.every((r) => trajSelected.has(r.path));
    folderCb.indeterminate = !folderCb.checked && runs.some((r) => trajSelected.has(r.path));
    folderCb.addEventListener("change", () => {
      for (const r of runs) { folderCb.checked ? trajSelected.add(r.path) : trajSelected.delete(r.path); }
      renderTrajTree();
    });
    const kids = runs.map((r) => {
      const cb = el("input", { type: "checkbox" });
      cb.checked = trajSelected.has(r.path);
      cb.addEventListener("change", () => {
        cb.checked ? trajSelected.add(r.path) : trajSelected.delete(r.path);
        renderTrajTree();
      });
      return el("label", { className: "traj-run" }, cb, el("span", { className: "name" }, r.name));
    });
    box.append(el("div", { className: "traj-folder" },
      el("label", { className: "traj-folder-head" }, folderCb, el("strong", {}, folder.name),
        el("span", { className: "muted tiny" }, ` ${runs.length} run(s)`)),
      el("div", { className: "traj-runs" }, ...kids)
    ));
  }
  $("#traj-tree-wrap").hidden = false;
  syncTrajSubmit();
}

$("#traj-select-all").addEventListener("click", () => {
  for (const f of trajTree?.folders || []) for (const r of f.runs || []) trajSelected.add(r.path);
  renderTrajTree();
});
$("#traj-select-none").addEventListener("click", () => { trajSelected.clear(); renderTrajTree(); });

$("#traj-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  const name = currentTrajProjectName();
  const status = $("#traj-upload-status");
  if (!name) { status.textContent = "pick a project first"; return; }
  status.textContent = "uploading…";
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await api(`/api/projects/${encodeURIComponent(name)}/jobs`, { method: "POST", body: fd });
    status.textContent = `added ${r.added.length} folder(s)`;
    setTrajTree(r.tree);
  } catch (err) { status.textContent = `error: ${err.message}`; }
});

$("#traj-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const p = currentTrajProject();
  const out = $("#traj-result");
  if (!p) { out.className = "result err"; out.textContent = "Pick a project first."; return; }
  if (trajSelected.size === 0) { out.className = "result err"; out.textContent = "Select at least one run."; return; }
  const fd = new FormData();
  fd.append("project_name", p.name);
  const tid = $("#traj-task").value;
  if (tid) fd.append("task_id", tid);
  const email = $("#reviewer-email").value.trim();
  if (email) fd.append("reviewer_email", email);
  fd.append("selected", JSON.stringify([...trajSelected]));
  out.className = "result"; out.textContent = "Submitting…";
  try {
    const r = await api("/api/execute-trajectory", { method: "POST", body: fd });
    out.className = "result ok";
    out.textContent = `Queued trajectory analysis — run ${r.run_id.slice(0, 8)}`;
    watchRun(r.run_id);
    loadRuns();
  } catch (e) { out.className = "result err"; out.textContent = `Error: ${e.message}`; }
});

/* ── runs table + run detail ─────────────────────────────────────────────── */
let pollTimer = null;
let activeRunId = null;
let runListTimer = null;
let lastReport = null;
let lastStatus = null;
let logOffset = 0;

const TERMINAL = ["passed", "failed", "error", "cancelled"];
const isActive = (state) => !TERMINAL.includes(state);

async function runTask(project, taskId) {
  const email = $("#reviewer-email").value.trim();
  try {
    const r = await api("/api/execute", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_name: project,
        project_type: trainerProjects.find((p) => p.name === project)?.type,
        reviewer_email: email || null, is_gcs: false, data: { task_id: taskId },
      }),
    });
    watchRun(r.run_id);
    loadRuns();
  } catch (e) {
    $("#run-detail").hidden = false;
    $("#run-status").replaceChildren(el("span", { className: "result err" }, `Error: ${e.message}`));
  }
}

function setStopEnabled(on) { $("#stop-run").disabled = !on; }

$("#stop-run").addEventListener("click", async () => {
  if (!activeRunId) return;
  setStopEnabled(false);
  try { await api(`/api/runs/${activeRunId}/cancel`, { method: "POST" }); }
  catch (e) { $("#run-status").append(el("span", { className: "result err" }, ` — ${e.message}`)); }
});

$("#close-run").addEventListener("click", () => {
  clearInterval(pollTimer);
  activeRunId = null;
  $("#run-detail").hidden = true;
  $$("#runs-tbody tr").forEach((r) => r.classList.remove("selected"));
});

function watchRun(runId) {
  clearInterval(pollTimer);
  activeRunId = runId;
  $("#run-detail").hidden = false;
  $("#run-log").textContent = "";
  lastReport = null;
  logOffset = 0;
  const tick = async () => {
    let status;
    try { status = await api(`/api/runs/${runId}`); }
    catch { clearInterval(pollTimer); return; }
    renderStatus(status);
    const chunk = await api(`/api/runs/${runId}/log?offset=${logOffset}`).catch(() => null);
    if (chunk && chunk.text) {
      logOffset = chunk.offset;
      const pre = $("#run-log");
      pre.textContent += chunk.text;
      pre.scrollTop = pre.scrollHeight;
    }
    setStopEnabled(isActive(status.state));
    if (!isActive(status.state)) {
      clearInterval(pollTimer);
      setStopEnabled(false);
      loadRuns();
      api(`/api/runs/${runId}/report`).then((rep) => { lastReport = rep; renderReport(rep); }).catch(() => {});
    }
  };
  tick();
  pollTimer = setInterval(tick, 2000);
  loadRuns();
}

function elapsedOf(s) {
  const start = Date.parse(s.started_at || s.created_at);
  if (!start) return "";
  const end = s.finished_at ? Date.parse(s.finished_at) : Date.now();
  const secs = Math.max(0, Math.round((end - start) / 1000));
  const m = Math.floor(secs / 60);
  return m ? `${m}m ${secs % 60}s` : `${secs}s`;
}

function timeShort(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function legDot(state) {
  const map = { passed: "✓", failed: "✗", skipped: "–", running: "◐", pending: "·", interrupted: "!", cancelled: "⊘", error: "✗" };
  return el("span", { className: `legdot ${state}`, title: state }, map[state] ?? "·");
}

/* filter state */
const filters = { state: "", project: "", q: "" };
$("#run-filter-state").addEventListener("change", (e) => { filters.state = e.target.value; loadRuns(); });
$("#run-filter-project").addEventListener("change", (e) => { filters.project = e.target.value; loadRuns(); });
let searchTimer = null;
$("#run-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { filters.q = e.target.value.trim().toLowerCase(); loadRuns(); }, 150);
});
$("#runs-refresh").addEventListener("click", loadRuns);

async function loadRuns() {
  const limit = 200;
  const runs = await api(`/api/runs?limit=${limit}`).catch(() => []);
  const tbody = $("#runs-tbody");
  tbody.replaceChildren();
  if (!runs.length) {
    tbody.append(el("tr", {}, el("td", { colSpan: 8, className: "muted empty" }, "No runs yet.")));
    return;
  }
  const filtered = runs.filter((r) => {
    if (filters.state && r.state !== filters.state) return false;
    if (filters.project && r.project !== filters.project) return false;
    if (filters.q) {
      const hay = `${r.task_id || ""} ${r.run_id || ""} ${r.project || ""}`.toLowerCase();
      if (!hay.includes(filters.q)) return false;
    }
    return true;
  });
  if (!filtered.length) {
    const hidden = runs.length;
    const hasFilter = filters.state || filters.project || filters.q;
    const cell = el("td", { colSpan: 8, className: "muted empty" });
    if (hasFilter) {
      cell.append(
        `${hidden} run(s) hidden by filter. `,
        el("a", { href: "#", onclick: (ev) => { ev.preventDefault(); filters.state = ""; filters.project = ""; filters.q = ""; $("#run-filter-state").value = ""; $("#run-filter-project").value = ""; $("#run-search").value = ""; loadRuns(); } }, "Clear filters")
      );
    } else {
      cell.textContent = "No runs yet.";
    }
    tbody.append(el("tr", {}, cell));
    return;
  }
  for (const r of filtered) {
    const legs = r.legs || {};
    const kind = r.kind || "review";
    const row = el("tr", { className: r.run_id === activeRunId ? "selected" : "", onclick: () => watchRun(r.run_id) },
      el("td", { className: "col-task" }, el("span", { className: "name", title: r.task_id || "(trajectories only)" }, r.task_id || "(trajectories only)")),
      el("td", { className: "col-project muted" }, r.project || ""),
      el("td", { className: "col-kind" }, badge(kind, kind)),
      el("td", {}, badge(r.state, r.state)),
      el("td", { className: "col-legs leg-cell" }, renderLegs(legs)),
      el("td", { className: "col-elapsed elapsed" }, elapsedOf(r)),
      el("td", { className: "col-created muted" }, timeShort(r.created_at)),
      el("td", { className: "col-actions" }, isActive(r.state)
        ? el("button", { className: "danger tiny", onclick: async (ev) => {
            ev.stopPropagation();
            try { await api(`/api/runs/${r.run_id}/cancel`, { method: "POST" }); } catch {}
            loadRuns();
          }}, "Stop")
        : el("span", { className: "muted tiny" }, r.run_id.slice(0, 8)))
      );
    tbody.append(row);
  }
}

function renderLegs(legs) {
  const names = Object.keys(legs);
  if (!names.length) return el("span", { className: "muted" }, "—");
  const frag = el("span", {});
  for (const k of names) {
    const st = legs[k]?.state;
    frag.append(
      legDot(st),
      el("span", { className: "leg-lbl" }, k.slice(0, 3))
    );
  }
  return frag;
}

function syncRunListTimer() {
  clearInterval(runListTimer);
  if ($("#auto-refresh").checked) runListTimer = setInterval(loadRuns, 5000);
}
$("#auto-refresh").addEventListener("change", syncRunListTimer);

/* subtabs */
$$("#detail-tabs .subtab").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#detail-tabs .subtab").forEach((x) => x.classList.toggle("active", x === b));
    $$(".subpanel").forEach((p) => { p.hidden = p.id !== `dtab-${b.dataset.dtab}`; });
  })
);

function renderStatus(s) {
  lastStatus = s;
  const running = isActive(s.state);
  $("#run-status").replaceChildren(
    running ? el("span", { className: "spin" }, "◐") : el("span", {}, ""),
    el("strong", {}, ` ${s.project} / ${s.task_id} `),
    badge(s.state, s.state),
    el("span", { className: "muted elapsed" }, ` ${elapsedOf(s)}`),
    el("span", { className: "muted" }, ` · run ${s.run_id.slice(0, 8)}${s.reviewer_email ? ` · ${s.reviewer_email}` : ""}`)
  );
  renderOverview();
  renderHarborPanel(s);
}

function renderOverview() {
  const s = lastStatus;
  if (!s) return;
  const box = $("#dtab-overview");
  const kids = [];
  if (lastReport) kids.push(el("div", { className: `banner ${lastReport.passed ? "pass" : "fail"}` }, lastReport.passed ? "PASS" : "FAIL"));
  const legNames = Object.keys(s.legs || {});
  kids.push(el("div", { className: "legs" },
    ...legNames.map((k) =>
      el("div", { className: "leg" },
        el("div", { className: "leg-name" }, k, " ", badge(s.legs[k].state, s.legs[k].state)),
        el("div", { className: "leg-summary" }, s.legs[k].summary || "")
      ))
  ));
  box.replaceChildren(...kids);
}

function renderReport(rep) {
  lastReport = rep;
  renderOverview();

  const det = rep.deterministic;
  const common = (det?.checks || []).filter((c) => c.source === "common");
  const specific = (det?.checks || []).filter((c) => c.source !== "common");

  const checkTable = (rows, title) => {
    const wrap = el("div", {});
    wrap.append(el("h3", {}, `${title} (${rows.length})`));
    if (!rows.length) { wrap.append(el("p", { className: "muted" }, "none")); return wrap; }
    const failOnly = el("input", { type: "checkbox" });
    const tbody = el("tbody", {});
    const fill = () => {
      tbody.replaceChildren();
      for (const c of rows) {
        if (failOnly.checked && c.passed) continue;
        tbody.append(el("tr", { className: c.passed ? "row-pass" : "row-fail" },
          el("td", {}, c.name),
          el("td", {}, badge(c.passed ? "pass" : "fail")),
          el("td", { className: "out" }, (c.output || "").slice(0, 500))
        ));
      }
    };
    failOnly.addEventListener("change", fill);
    wrap.append(el("label", { className: "inline-toggle" }, failOnly, " failures only"));
    wrap.append(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Check"), el("th", {}, "Result"), el("th", {}, "Output"))),
      tbody));
    fill();
    return wrap;
  };

  const checksBox = $("#dtab-checks");
  checksBox.replaceChildren(checkTable(specific, "Project checks"), checkTable(common, "Common checks"));

  const rubBox = $("#dtab-rubric");
  if (rep.rubric?.skipped) {
    rubBox.replaceChildren(el("p", { className: "muted" }, `skipped — ${rep.rubric.skip_reason}`));
  } else {
    rubBox.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Criterion"), el("th", {}, "Verdict"), el("th", {}, "Reason"))),
      el("tbody", {}, ...(rep.rubric?.verdicts || []).map((v) =>
        el("tr", { className: v.verdict === "pass" ? "row-pass" : "row-fail" },
          el("td", {}, v.name), el("td", {}, badge(v.verdict)), el("td", { className: "out" }, v.reason || ""))))
    ));
  }

  const valBox = $("#dtab-validation");
  if (rep.validation?.skipped) {
    valBox.replaceChildren(el("p", { className: "muted" }, `skipped — ${rep.validation.skip_reason}`));
  } else {
    const v = rep.validation || {};
    valBox.replaceChildren(
      el("table", {},
        el("tr", {}, el("th", {}, "oracle reward"), el("td", {}, String(v.oracle_reward ?? ""))),
        el("tr", {}, el("th", {}, "nop reward"), el("td", {}, String(v.nop_reward ?? ""))),
        el("tr", {}, el("th", {}, "details"), el("td", { className: "out" }, v.details || ""))
      )
    );
  }

  renderTrajectoryTab(rep);
}

function renderTrajectoryTab(rep) {
  const box = $("#dtab-trajectory");
  const traj = rep.trajectory;
  if (!traj) { box.replaceChildren(el("p", { className: "muted" }, "Not a trajectory analysis run.")); return; }
  if (traj.skipped) {
    box.replaceChildren(el("p", { className: "muted" }, `skipped — ${traj.skip_reason}`));
    return;
  }
  const kids = [];
  if (traj.job_summary) {
    kids.push(el("h3", {}, "Job summary"));
    kids.push(el("p", { className: "readonly" }, traj.job_summary));
  }
  const trials = traj.trials || [];
  kids.push(el("h3", {}, `Trials (${trials.length})`));
  if (!trials.length) {
    kids.push(el("p", { className: "muted" }, "no trials"));
  }
  for (const t of trials) {
    const fails = (t.checks || []).filter((c) => c.verdict === "fail");
    kids.push(el("div", { className: "trial-block" },
      el("div", { className: "trial-head" },
        el("strong", {}, t.name),
        el("span", { className: "muted" }, ` · ${t.checks?.length || 0} checks · ${fails.length} fail`)
      ),
      t.summary ? el("p", { className: "readonly" }, t.summary) : el("span"),
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Criterion"), el("th", {}, "Verdict"), el("th", {}, "Explanation"))),
        el("tbody", {}, ...(t.checks || []).map((c) =>
          el("tr", { className: c.verdict === "pass" ? "row-pass" : (c.verdict === "not_applicable" ? "row-skip" : "row-fail") },
            el("td", {}, c.name), el("td", {}, badge(c.verdict)), el("td", { className: "out" }, c.reason || "")
          )
        ))
      )
    ));
  }
  box.replaceChildren(...kids);
}

function renderHarborPanel(s) {
  const box = $("#dtab-harbor");
  const jobsPath = s.harbor_jobs;
  if (!jobsPath) {
    box.replaceChildren(el("p", { className: "muted" }, "No Harbor job artifacts persisted for this run."));
    return;
  }
  const cmd = `harbor view --jobs ${jobsPath}`;
  box.replaceChildren(
    el("p", {}, el("strong", {}, "Harbor jobs"), el("span", { className: "muted" }, " — persisted oracle/nop/check job trees")),
    el("p", { className: "kv" }, "Path: ", el("code", {}, jobsPath)),
    el("p", {}, "View in Harbor:"),
    el("pre", { className: "copyable", onclick: (e) => { navigator.clipboard?.writeText(cmd); e.target.classList.add("copied"); } }, cmd),
    el("p", { className: "muted" }, "Click the command to copy. Or merge all runs: ./view-runs.sh")
  );
}

/* ── docker housekeeping ────────────────────────────────────────────────── */
async function loadDockerState() {
  const box = $("#docker-state");
  box.textContent = "Checking…";
  try {
    const d = await api("/api/maintenance/docker");
    const running = d.containers.filter((c) => c.running);
    const stopped = d.containers.filter((c) => !c.running);
    box.replaceChildren(
      el("div", {}, `${running.length} running, ${stopped.length} stopped, ${d.networks.length} network(s).`),
      running.length ? el("div", { className: "muted" }, `running: ${running.map((c) => c.name).join(", ")}`) : el("span"),
      el("div", { className: "muted" }, d.reclaimable ? `${d.reclaimable} item(s) reclaimable.` : "Nothing to clean up.")
    );
  } catch (e) { box.className = "result err"; box.textContent = `Error: ${e.message}`; }
}
$("#docker-refresh").addEventListener("click", loadDockerState);
$("#docker-cleanup").addEventListener("click", async () => {
  const out = $("#docker-result");
  out.className = "result"; out.textContent = "Cleaning…";
  try {
    const r = await api("/api/maintenance/docker/cleanup", { method: "POST" });
    out.className = "result ok";
    out.textContent = r.removed.length ? `Removed: ${r.removed.join(", ")}` : "Nothing to remove.";
    if (r.skipped.length) out.textContent += ` — left: ${r.skipped.join(", ")}`;
    loadDockerState();
  } catch (e) { out.className = "result err"; out.textContent = `Error: ${e.message}`; }
});

/* ── boot ───────────────────────────────────────────────────────────────── */
loadProjects();
loadTrainerProjects();
syncRunListTimer();
