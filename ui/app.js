/* Rudimentary test UI for the autoreviewer API.
   No build step: plain DOM, fetch, and polling. */

const $ = (sel) => document.querySelector(sel);
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
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-panel").forEach((p) =>
      p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`)
    );
    if (tab.dataset.tab === "trainer") { loadTrainerProjects(); loadRuns(); }
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

  // Build the multipart body by hand: skip empty file inputs and the empty
  // validation_mode option, which FastAPI would otherwise reject as invalid.
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
    const li = el("li", { className: p.name === selectedProject ? "selected" : "" },
      el("span", { className: "name", onclick: () => showProject(p.name) }, p.name),
      badge(p.type, p.type),
      el("span", { className: "muted" }, `${p.tasks} tasks · ${p.project_checks + p.common_checks} checks`)
    );
    list.append(li);
  }
}

async function showProject(name) {
  selectedProject = name;
  await loadProjects();
  const box = $("#project-detail");
  box.replaceChildren(el("p", { className: "muted" }, "Loading…"));
  const p = await api(`/api/projects/${encodeURIComponent(name)}`);

  const rubricLine = p.has_rubric
    ? `${p.rubric_path} — ${p.rubric_criteria.length} criteria`
    : "no rubric yet";

  box.replaceChildren(
    el("h3", {}, "Detail"),
    el("p", { className: "kv" }, `${p.type} · validation: ${p.validation_mode} · ${p.description || "no description"}`),
    el("p", { className: "kv" }, `Rubric: ${rubricLine}`),
    p.rubric_criteria.length
      ? el("ul", { className: "list" }, p.rubric_criteria.map((c) => el("li", {}, el("span", {}, c))))
      : el("span"),

    el("h3", {}, "Project checks"),
    checksList(p),
    el("form", { id: "add-check-form" },
      el("label", {}, "Add checks (.sh / .py)",
        el("input", { type: "file", name: "files", multiple: true, accept: ".sh,.py" })),
      el("button", { type: "submit", className: "ghost" }, "Upload checks")
    ),
    el("div", { id: "check-result", className: "result" }),

    p.common_check_names.length
      ? el("details", {},
          el("summary", {}, `Inherited common checks (${p.common_check_names.length})`),
          el("p", { className: "readonly" }, "From the repo-root checks/ set — read-only here. A project check with the same filename overrides one."),
          el("ul", { className: "list" }, p.common_check_names.map((c) => el("li", {}, el("span", {}, c), badge("common", "skip"))))
        )
      : el("p", { className: "muted" }, "This project runs only its own checks."),

    el("h3", {}, "Rubric source"),
    el("pre", { id: "rubric-src" }, p.has_rubric ? "" : "(none)")
  );

  if (p.has_rubric) {
    api(`/api/projects/${encodeURIComponent(name)}/rubric`)
      .then((r) => { $("#rubric-src").textContent = r.content; })
      .catch(() => {});
  }

  $("#add-check-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = ev.target.querySelector("input[type=file]");
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("files", f);
    const out = $("#check-result");
    try {
      const r = await api(`/api/projects/${encodeURIComponent(name)}/checks`, { method: "POST", body: fd });
      out.className = "result ok";
      out.textContent = `Uploaded: ${r.written.join(", ")}`;
      await showProject(name);
    } catch (e) {
      out.className = "result err";
      out.textContent = `Error: ${e.message}`;
    }
  });
}

function checksList(p) {
  if (!p.project_check_names.length) {
    return el("p", { className: "muted" }, "No project-specific checks uploaded.");
  }
  return el("ul", { className: "list" }, p.project_check_names.map((c) =>
    el("li", {}, el("span", {}, c),
      el("button", {
        className: "ghost tiny",
        onclick: async () => {
          await api(`/api/projects/${encodeURIComponent(p.name)}/checks/${encodeURIComponent(c)}`, { method: "DELETE" });
          showProject(p.name);
        },
      }, "Delete"))
  ));
}

$("#refresh-projects").addEventListener("click", loadProjects);

/* ── trainer ────────────────────────────────────────────────────────────── */
let trainerProjects = [];

async function loadTrainerProjects() {
  trainerProjects = await api("/api/projects");
  const sel = $("#trainer-project");
  const previous = sel.value;
  sel.replaceChildren(...trainerProjects.map((p) => el("option", { value: p.name }, `${p.name} (${p.type})`)));
  if (trainerProjects.some((p) => p.name === previous)) sel.value = previous;
  syncTrainerHint();
  await loadTasks();
}

function currentProject() {
  return trainerProjects.find((p) => p.name === $("#trainer-project").value);
}

function syncTrainerHint() {
  const p = currentProject();
  $("#trainer-hint").textContent = p
    ? `${p.type} · ${p.project_checks} project check(s) + ${p.common_checks} common · rubric ${p.has_rubric ? "present" : "MISSING"}`
    : "No projects yet — create one in the Delivery Manager tab.";
}

$("#trainer-project").addEventListener("change", () => { syncTrainerHint(); loadTasks(); loadRuns(); });

async function loadTasks() {
  const list = $("#task-list");
  list.replaceChildren();
  const p = currentProject();
  if (!p) return;
  const { tasks } = await api(`/api/projects/${encodeURIComponent(p.name)}/tasks`);
  if (!tasks.length) {
    list.append(el("li", {}, el("span", { className: "muted" }, "No tasks uploaded yet.")));
    return;
  }
  for (const t of tasks) {
    list.append(el("li", {},
      el("span", { className: "name", title: t }, t),
      el("button", { className: "primary tiny", onclick: () => runTask(p.name, t) }, "Run review"),
      el("button", {
        className: "ghost tiny",
        onclick: async () => {
          if (!confirm(`Delete task ${t}? This removes it from disk.`)) return;
          await api(`/api/projects/${encodeURIComponent(p.name)}/tasks/${encodeURIComponent(t)}`, { method: "DELETE" });
          loadTasks();
        },
      }, "Delete")
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
  out.className = "result";
  out.textContent = "Uploading…";
  try {
    const r = await api(`/api/projects/${encodeURIComponent(p.name)}/tasks`, { method: "POST", body: fd });
    out.className = "result ok";
    out.textContent = `Uploaded ${r.task_id} (${r.kind})${r.contents ? ` — ${r.contents.join(", ")}` : ""}`;
    ev.target.reset();
    await loadTasks();
  } catch (e) {
    out.className = "result err";
    out.textContent = `Error: ${e.message}`;
  }
});

/* ── runs ───────────────────────────────────────────────────────────────── */
let pollTimer = null;

async function runTask(project, taskId) {
  clearInterval(pollTimer);
  $("#run-report").replaceChildren();
  $("#run-log").textContent = "";
  $("#run-status").textContent = "Queuing…";
  const email = $("#reviewer-email").value.trim();
  try {
    const r = await api("/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_name: project,
        project_type: currentProject()?.type,
        reviewer_email: email || null,
        is_gcs: false,
        data: { task_id: taskId },
      }),
    });
    watchRun(r.run_id);
    loadRuns();
  } catch (e) {
    $("#run-status").replaceChildren(el("span", { className: "result err" }, `Error: ${e.message}`));
  }
}

function watchRun(runId) {
  clearInterval(pollTimer);
  let offset = 0;
  const tick = async () => {
    let status;
    try {
      status = await api(`/api/runs/${runId}`);
    } catch { clearInterval(pollTimer); return; }
    renderStatus(status);

    const chunk = await api(`/api/runs/${runId}/log?offset=${offset}`).catch(() => null);
    if (chunk && chunk.text) {
      offset = chunk.offset;
      const pre = $("#run-log");
      pre.textContent += chunk.text;
      pre.scrollTop = pre.scrollHeight;
    }

    if (["passed", "failed", "error"].includes(status.state)) {
      clearInterval(pollTimer);
      loadRuns();
      if (status.state !== "error") {
        api(`/api/runs/${runId}/report`).then(renderReport).catch(() => {});
      }
    }
  };
  tick();
  pollTimer = setInterval(tick, 2000);
}

function renderStatus(s) {
  $("#run-status").replaceChildren(
    el("strong", {}, `${s.project} / ${s.task_id} `),
    badge(s.state, s.state),
    el("span", { className: "muted" }, ` run ${s.run_id.slice(0, 8)}${s.reviewer_email ? ` · ${s.reviewer_email}` : ""}`)
  );
  $("#run-legs").replaceChildren(
    ...["deterministic", "rubric", "validation"].map((k) =>
      el("div", { className: "leg" },
        el("div", { className: "leg-name" }, k, " ", badge(s.legs[k].state, s.legs[k].state)),
        el("div", { className: "leg-summary" }, s.legs[k].summary || "")
      )
    )
  );
}

function renderReport(rep) {
  const box = $("#run-report");
  const det = rep.deterministic;
  const common = det.checks.filter((c) => c.source === "common");
  const specific = det.checks.filter((c) => c.source !== "common");

  const checkTable = (rows, title) =>
    rows.length
      ? el("div", {},
          el("h3", {}, title),
          el("table", {},
            el("tr", {}, el("th", {}, "Check"), el("th", {}, "Result"), el("th", {}, "Output")),
            ...rows.map((c) =>
              el("tr", {},
                el("td", {}, c.name),
                el("td", {}, badge(c.passed ? "pass" : "fail")),
                el("td", { className: "out" }, (c.output || "").slice(0, 400))
              )
            )
          ))
      : el("span");

  box.replaceChildren(
    el("div", { className: `banner ${rep.passed ? "pass" : "fail"}` }, rep.passed ? "PASS" : "FAIL"),
    checkTable(specific, `Project checks (${specific.length})`),
    checkTable(common, `Common checks (${common.length})`),
    el("h3", {}, "Rubric"),
    rep.rubric.skipped
      ? el("p", { className: "muted" }, `skipped — ${rep.rubric.skip_reason}`)
      : el("table", {},
          el("tr", {}, el("th", {}, "Criterion"), el("th", {}, "Verdict"), el("th", {}, "Reason")),
          ...rep.rubric.verdicts.map((v) =>
            el("tr", {},
              el("td", {}, v.name),
              el("td", {}, badge(v.verdict)),
              el("td", { className: "out" }, v.reason || "")
            )
          )
        ),
    el("h3", {}, "Validation"),
    el("p", { className: "kv" },
      rep.validation.skipped
        ? `skipped — ${rep.validation.skip_reason}`
        : `oracle=${rep.validation.oracle_reward} nop=${rep.validation.nop_reward} — ${rep.validation.details}`)
  );
}

async function loadRuns() {
  const p = currentProject();
  const runs = await api(`/api/runs?limit=15${p ? `&project=${encodeURIComponent(p.name)}` : ""}`).catch(() => []);
  const list = $("#run-list");
  list.replaceChildren();
  if (!runs.length) { list.append(el("li", {}, el("span", { className: "muted" }, "No runs yet."))); return; }
  for (const r of runs) {
    list.append(el("li", {},
      el("span", { className: "name", onclick: () => watchRun(r.run_id) }, r.task_id),
      badge(r.state, r.state),
      el("span", { className: "muted" }, r.created_at)
    ));
  }
}

/* ── boot ───────────────────────────────────────────────────────────────── */
loadProjects();
loadTrainerProjects();
