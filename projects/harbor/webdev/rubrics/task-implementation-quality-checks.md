# Task Implementation — Quality Checks (Plain-English Summary)

A quick reference for the WebDev browser-judged task rubric. Each item is one quality check (`pass` / `fail` / `not_applicable`). Full guidance lives in `task-implementation.toml`; this file just says **what each check is looking for**.

The whole rubric protects one idea — the **two-sided gate**:
- **Oracle high** → a correct reference app scores near the top.
- **Floor low** → a blank / fake / stub / keyword-stuffed app scores near zero.

> **Network is PUBLIC in this project.** `network_mode = "public"` on both the agent and the verifier is correct. Do **not** flag a public network mode, a missing allowlist, an external CDN/font/script/API fetch, or a lack of same-origin/offline. None of these is a defect here.

---

## Block A — `instruction.md` (is the prompt a real, fair, natural ask?)

- **instruction_is_a_natural_product_request** — The prompt reads like a real person asking for an app, not a spec sheet, checklist, or build recipe.
- **instruction_preserves_natural_human_voice** — Keeps an authentic human voice (casual/terse is good); not robotic, over-polished, or LLM-generated prose.
- **instruction_is_spelled_right_and_uncontaminated** — No real spelling errors and nothing pasted in by mistake (author notes, TODOs, other machines' paths, contradictions).
- **instruction_states_deliverables_and_runtime_contract** — Everything the judges grade is actually asked for, and the hard runtime facts the verifier needs (path, start command, port, storage, seed, accounts) are stated. (Network is public in this project — no no-network constraint to state.)
- **instruction_leaks_no_grader_machinery** — The prompt never names the judge, rubric, dimensions, weights, test paths, or grader sentinels.
- **instruction_is_achievable_and_unambiguous_in_the_environment** — One reasonable reading, and every capability is reachable from the seed, the provided runtime, or the public internet (network is allowed). (Reports *every* ambiguity/unreachable item.)
- **task_asks_for_a_real_working_product** — Real build work is required; a stub or trivial tweak can't earn the reward.

## Block B — `task.toml` and run wiring (is the run set up correctly?)

- **task_identity_is_coherent** — Name, directory slug, description, keywords, and metadata all describe THIS task and agree.
- **agent_environment_and_network_posture_are_correct** — Agent image has sane CPU/memory and no secret literals. Network is public here, so `network_mode = "public"` is correct — do not flag it.
- **verifier_is_isolated_pinned_and_credentialed** — Verifier runs separately on a pinned image with the judge model and API key fully wired. Network is public — `network_mode = "public"` is correct and no allowlist is required.
- **timeouts_fit_the_work** — Agent, verifier, liveness, and judge timeouts are long enough and nest properly (inner < outer, sum of judges < verifier).
- **no_prebuilt_image_shadows_the_agent_dockerfile** — `[environment].docker_image` isn't set while the agent Dockerfile still has active build steps (which would skip the Dockerfile entirely).

## Block C — `environment/` (assets and the agent image)

- **assets_match_the_task** — Any shipped inputs exist at the expected path and their content matches what the prompt, solution, and judges assume (or N/A if none needed).
- **seed_data_is_internally_consistent_and_clean** — Shipped data is self-consistent, synthetic (no real PII), and free of orphan references or injection payloads.
- **dockerfile_builds_the_declared_world** — Agent image is pinned, pre-installs every runtime dependency (no run-time install), and stages the assets.
- **environment_does_not_leak_the_answer** — The agent's world has the inputs and the ask, but no finished copy of the deliverable.

## Block D — `solution/` (does the reference app cover everything? — coverage, not line audit)

- **solution_covers_every_deliverable** — The reference plausibly implements every feature/screen the instruction asks for.
- **solution_covers_every_graded_dimension** — The reference plausibly satisfies every criterion the judges score, so the oracle can score high.
- **solution_honors_the_runtime_contract_and_is_self_contained** — `solve.sh` installs to the expected paths and the reference runs under the stated contract. (Network is public — fetching or installing at start is not a defect.)
- **solution_is_frozen_and_deterministic** — The reference is a committed, static baseline — not regenerated, fetched, or nondeterministic on any pinned value.

## Block E — `tests/` (the verifier and browser-judge dimensions)

- **verifier_entrypoint_is_safe_and_always_scores** — `test.sh` launches the app safely, gates on liveness, and writes a reward on every code path (including failures).
- **verifier_image_can_launch_and_grade** — The verifier Dockerfile ships a pinned browser, Playwright, judge CLI, rewardkit, and the runtime needed to start the app.
- **verifier_and_instruction_agree_on_the_runtime_contract** — Every launch assumption in `test.sh` (probe URL, env vars, paths, seed, deps) is something the instruction told the agent to satisfy. (No same-origin requirement — network is public.) *(The signature check of this format.)*
- **grading_wiring_is_structurally_correct** — `reward.toml` and every `judge.toml` are structurally complete: pinned judge, a browser MCP server, well-typed criteria with weights, valid aggregate.
- **judge_prompts_drive_the_browser** — Every dimension prompt sends the judge into the live app via the browser tool — not scoring from source, memory, or a first-paint guess.
- **dimensions_cover_every_graded_requirement** — Every requirement the prompt states maps to at least one criterion (no asked-for behavior goes ungraded). Reports *every* gap.
- **no_criterion_grades_the_unrequired** — No criterion enforces something the prompt/professional default never required (no false-fail on correct apps). Reports *every* instance.
- **criteria_are_independent_and_noncontradictory** — No two criteria grade the same thing twice, subsume each other, or demand incompatible products.
- **global_browser_gate_is_present_and_correct_in_every_dimension** — Every dimension carries the browser gate that hard-zeros blank/static-shell apps (plus auth/backing checks when the app has them). Network is public, so the gate must NOT require same-origin.
- **negative_checks_have_positive_controls** — Any "rejects / hides / absent" check is paired with the matching success case, so a totally broken app can't earn it.
- **plural_asks_are_checked_across_all_matches** — "Every / all / only / exactly-one" criteria require the whole collection, and "unchanged" guards don't punish legitimate side-effects. Reports *every* instance.
- **criteria_are_outcome_based_and_browser_decidable** — Each criterion is a concrete, browser-observable outcome with durable evidence and distinctive probes. Reports *every* instance.
- **criterion_description_is_self_consistent** — Each criterion states ONE full-credit bar — it doesn't enumerate several things then waive most, leaving the judge two targets. Reports *every* instance.
- **interactive_time_varying_and_viewport_behavior_is_exercised** — If interactive/animated/responsive/themed, the judges actually click, wait, resize, or toggle — not score a still first paint.
- **core_behavior_is_graded_and_state_is_proven_durable_where_it_must_be** — At least one criterion proves the product's defining behavior works, and (where stateful) that state survives a reload / re-auth and is server-backed where required. (Server-backed ≠ same-origin — network is public.)
- **grader_probes_are_not_pre_satisfied** — Distinctive values the judge creates to prove a mutation aren't already sitting in the seed or the reference's initial state.
- **later_dimensions_tolerate_earlier_mutations** — A later dimension doesn't assume a pristine seed after an earlier dimension mutated the shared running app.
- **batched_criteria_are_scored_independently** — Batched dimension prompts tell the judge to score each criterion on its own and continue after a failure (one miss can't zero the rest).
- **floor_is_low_for_shells_mocks_and_stuffing** — A blank / static / mock / seed-copy / keyword-stuffed / refusing submission scores near zero across the rubric. (An off-origin/CDN fetch is NOT a floor case — network is public.)
- **reward_is_graded_not_binary_and_discriminates** — The rubric produces a spread across partial-quality apps, not all-or-nothing.
- **binary_and_likert_fit_the_ask** — Pass/fail behaviors are `binary`; craft and degree-of-quality are `likert` with described anchors.
- **reward_ranking_is_monotone** — A worse app never outscores a better one — weights/gates/criteria don't invert the ranking.
- **gates_apply_before_shaping_and_carry_no_reward_mass** — Gate/constraint failures hard-zero the quality terms, and passing only the cheap gates earns little.
- **dimension_and_criterion_weights_are_honest** — Weight tracks what each thing proves — real functionality is weighted above structure and style.
- **judges_are_injection_resistant** — Every dimension prompt treats the submission as untrusted and forbids following instructions embedded in it.
- **tests_and_key_are_out_of_agent_reach** — The agent can't read the criteria it's graded on or influence the reward — grading is isolated in the verifier.
- **verifier_is_deterministic_and_offline_pinned** — Pinned model, temperature 0, versioned prompt, pinned browser. Network is public here, so an open verifier network / missing allowlist is NOT a defect.
- **dimension_prompts_are_accurate_and_consistent** — Every dimension prompt describes THIS app (credentials, screens, entities, deliverable) with no residue from other work. Reports *every* instance.

## Block F — the task as a whole

- **cross_file_runtime_contract_is_consistent** — Every runtime fact that appears in more than one file (paths, port, seed, accounts, model, weights, literals) agrees everywhere. Reports *every* drift.
- **task_folder_holds_only_task_files** — The directory is the closed list — no scratch, build residue, committed caches, or backups, and all required files present.
- **everything_parses_and_would_run** — The gating files are well-formed: both TOML families, the shell scripts (`bash -n`, no CRLF), and the reference/app entry.
- **task_security_and_secrets** — No live credentials, real personal data, host paths, unpinned remote fetch, or injection payload anywhere in the task.
- **task_is_distinct_and_authored** — The task reads as authored for this product, fits the suite's domain plan, and isn't a nouns-swapped clone of a sibling.
