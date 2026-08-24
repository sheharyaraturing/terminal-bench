# NOTES — revert-reland-divergence

## Premise

A Release Engineer will not sign 1.11 until the draft notes are reconciled with
history and with the trees at each release tag. The instruction demands complete
churn sequences per behaviour; entry-path proof from complementary incomplete
history views; quoted removal reasons; landing blob identities; a full tag
inventory with VERSION-at-tag; per-behaviour release tables (pre-warm and
jitter at minimum); plain-vs-follow history counts; negative-search results for
decoy reverts; silent regressions the notes omit; and per-item note verdicts —
without naming the land/revert/re-land pattern or the commands that find it.

The design principle: **the cheapest correct-looking method must be wrong at
every layer.** A competent agent will reach for a small set of moves — grep the
subjects for "revert", read each commit's diffstat, trust a cherry-pick trailer,
ask `git tag --contains` which release shipped what, read a file's history at its
current path, treat a higher version number as a later state, believe the
changelog. Each of those is individually reasonable, and each is wrong about
something specific here:

| cheap move | what it says | what is true |
|---|---|---|
| grep subjects for revert | 4 candidates, 2 real | one removal never says "revert" (`de96d28`), one "revert of a revert" restores nothing (`c5e2305`), one "Revert to…" is a feature (`1a581a9`) |
| read each commit's diffstat | the two pre-warm landings are identical (both `10 0 src/pool.py`) | they differ by one line |
| trust the cherry-pick trailer | landing 2 is landing 1 | the trailer names `9d8b9f6` and the content is not it |
| `git tag --contains` | v1.8.0 and v1.9.1 shipped the pre-warm | neither has it; the removal is reachable too |
| version numbers imply lineage | v1.9.1 is v1.9.0 plus a fix | v1.9.1 was branched from the removal and never had the pre-warm |
| log a file at its path | the backoff module has 4 commits | it was renamed; `--follow` shows the rest |
| the changelog | 1.10.0 shipped jitter and configured warm-up | neither ever shipped at that tag |
| a tag names its version | v1.10.0 contains 1.10.0 | `VERSION` at `v1.10.0` is still `"1.9.0"` |

Layering: the churn sequence has to be complete before the divergence question
can be asked, the divergence has to be established before the release matrix
means anything, and the release matrix is what makes two of the note bullets
falsifiable. A model that closes the first tidy cycle — landed, reverted,
re-landed, shipped in 1.9.0 — banks very little and gets the 1.11 answer wrong.

## Fixture provenance

The repository is **synthetic and authored here**. No upstream project was
cloned; nothing was downloaded.

| artefact | injected as | measured size |
|---|---|---:|
| `fixtures/pipeline-svc.bundle` | `git clone` to `/data/repos/pipeline-svc` | **24,135 bytes** |
| `fixtures/GROUND_TRUTH.md` | not injected — authoring artefact | 22,692 bytes |

Build invocation:

```
bash environment/fixtures/build_fixture.sh
```

It was actually run. Contents: **56 commits on `main`**, 59 reachable from all
refs, **1 merge commit**, one empty commit, three authors, one commit whose
author is not its committer, ten tracked files, and **ten tags** — eight
lightweight, two annotated (`v1.10.0`, `v1.11.0`), one of which is not a version
number (`pipeline-1.11-rc1`). One branch, `hotfix/1.9.1`, is never merged, so
three of its commits and the `v1.9.1` tag are unreachable from `HEAD`.

**Pinned SHA** — the value in `environment/Dockerfile`:

```
aa86ca39961cd50b84023a9002fc38a6ac1054ba
```

`git cat-file -t` returns `commit` for it in a fresh clone of the bundle. The
Dockerfile also asserts the commit count (56), the merge count (1), the all-refs
count (59), the tag count (10), that `refs/tags/v1.10.0` is a **tag object** and
not a commit, and that `src/backoff.py` exists — that last one because the
rename is load-bearing for a claim and a fixture that shipped `src/retry.py`
would silently invalidate it.

**Object SHAs are reproducible; the bundle's bytes are not.** `git bundle create`
writes a pack, and pack encoding depends on the git version and on delta/thread
scheduling, so re-running the script emits a bundle of slightly different size
and checksum while carrying an identical object graph. Successive rebuilds on the
authoring host confirmed this directly. The committed bundle is therefore the
artefact of record and is not replaced casually; what gets re-run and re-checked
is the read-back stage. An earlier revision of this file claimed byte-identical
bundle reproduction, which was measured on one git version and does not
generalise.

Determinism of the objects themselves is enforced the same way as before, with
one addition for the new tag shapes: `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`
are both set on every commit in raw `@<epoch> +0000` form derived arithmetically
from the commit index; author and committer identity are set explicitly per
commit through a `who` helper (three authors, and one deliberate
author≠committer commit); merges are created with `--no-ff` under the same pinned
dates; the two **annotated** tags take their tagger identity and date from the
pinned committer environment, so their tag objects hash deterministically too;
`git commit --no-gpg-sign` runs with a scratch `HOME`, `GIT_CONFIG_GLOBAL` and
`GIT_CONFIG_SYSTEM=/dev/null`.

The bundle is created with `git bundle create ... --all` — **never `--depth 1`**.
`--all` is what carries `refs/tags/*` and the unmerged `hotfix/1.9.1` branch, and
both are load-bearing: the 1.9.1 lineage claim is unanswerable without the
branch, and the release matrix is unanswerable without the tags.

Two GNU-isms were removed so the script runs on macOS as well as Linux, neither
of which changes any object: `sed -i` (BSD sed reads the next argument as a
mandatory backup suffix) is now a `setver` helper that writes through a scratch
file and `cat`s it back in place, and `tac` is now `git log --reverse`.

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, and generated from the
bundle rather than from the builder's working tree. The read-back stage clones
`pipeline-svc.bundle` into a scratch directory, checks out the pinned SHA as
`main`, and runs the same commands an agent would: `git log` (plain,
`--first-parent`, `--follow`, `--all`, `--grep`), `git show`, `git diff`,
`git diff --numstat`, `git rev-parse <rev>:<path>`, `git cat-file -t`,
`git tag --contains`, `git merge-base --is-ancestor`. Whatever those print is the
file. Because two commits now share a subject, the read-back does **not** locate
commits by grep: every SHA is captured into a variable at the moment the commit
is created and then verified to exist in the clone.

The SHAs it produced, all of which appear in `tests/reward.toml`:

| short | role |
|---|---|
| `9d8b9f6` | pre-warm landing 1, on `feature/prewarm`, warms `max_size` |
| `5b35d23` | the only merge; brings landing 1 to main |
| `f0a6be7` | removal 1, a genuine back-out |
| `245abbe` | `POOL_WARM_TARGET = "min"` knob, one commit before landing 2 |
| `5b99564` | landing 2: same subject, false cherry-pick trailer, warms `min_size` |
| `de96d28` | removal 2, subject says "pool: simplify worker start-up" |
| `77b8763` | landing 3, `warm_target()` driven by config |
| `5f72d7d` / `3a3a3d0` | the 1.9.1 hotfix, once on the branch and once on main |
| `7cb3e9e` | `src/retry.py` -> `src/backoff.py` |
| `751bf03` / `121e367` | jitter landed / removed |
| `c5e2305` | "Revert of the revert" that restores nothing |
| `0b24074` | `resolved_shard()`, miscredited to 1.11.0 |
| `a4c24c9` | metrics subject with no metrics |
| `1a581a9` | decoy: "Revert to a single writer per shard" |
| `c62e5a5` / `03a1d46` | 1.10.0 changelog (the `v1.10.0` tag target) / the version bump after it |
| `aa86ca3` | HEAD / pinned branch tip |

and the facts:

- `git diff 9d8b9f6 5b99564 -- src/pool.py` is `1 1`: `self._prewarm(self.max_size)`
  became `self._prewarm(self.min_size)`. Pool blobs `73f71e9` then `c6431cd`
- each landing read alone is `10 0 src/pool.py` and touches nothing else
- `ConnectionPool.__init__` defaults are `min_size=2, max_size=32`
- `src/pool.py` at `f0a6be7` and at `9d8b9f6^` are the same blob `a2d81b3`, and
  `de96d28` returns the module to that same blob — the two removals are both real
- `de96d28` is `0 10 src/pool.py` and deletes `_prewarm()` and `start()`
- `77b8763` is a 20-insertion change adding `warm_target()`
- pre-warm presence by tag: absent v1.4.0–v1.8.0, `min_size` at v1.9.0, absent
  v1.9.1, absent v1.10.0, `warm_target()` at pipeline-1.11-rc1 and v1.11.0
- `git tag --contains 9d8b9f6` lists v1.8.0, v1.9.0, v1.9.1, v1.10.0, v1.11.0 and
  the rc tag — three of those have no pre-warm
- `git merge-base --is-ancestor v1.9.0 v1.9.1` is false
- `refs/tags/v1.10.0` is a tag object; `VERSION` at that tag is `"1.9.0"`
- `git log -- src/backoff.py` is 4 commits; `--follow` is 6
- `grep -c random` on the backoff module: 2 at `751bf03`, 0 at `121e367`, 0 at
  `c5e2305`, 0 at v1.10.0, v1.11.0 and HEAD; `121e367` restored the pre-jitter
  blob `bf6f257` exactly and the only later change is `c5e2305`'s two comment lines
- `def resolved_shard` is absent at v1.4.0–v1.7.0 and present from v1.8.0 on
- `a4c24c9` is `3 0 src/api.py`, entirely a TODO comment
- `1a581a9` is `12 0 src/shard.py`; `git log --all -i --grep='single writer'`
  returns only `1a581a9` itself

Read-back caught three things the build script did not guarantee. First, the
default `git log -- src/pool.py` **omits** the merge while `--first-parent`
**omits** the landing — the two-incomplete-views property was checked, not
assumed. Second, `resolved_shard()` ended up first shipping at **v1.8.0** rather
than v1.9.0, because the commit landed before the 1.8.0 release; the claim was
written from the read-back, not from the plan. Third, an earlier draft had commit
dates spaced two days apart, which pushed the whole history into May and left the
revert body quoting a deploy date that no longer matched any commit; spacing was
returned to three days and the body was rewritten to describe the deploy without
a date, so no claim depends on a date that a re-spacing would invalidate. The
changelog section headers also lost their planned dates for the same reason —
they were unclaimed noise that contradicted the commit dates.

## Difficulty design

15 claims, all equal weight (default 1.0). Dropping three gives 12/15 = 0.800;
dropping four gives 11/15 = 0.733. The 0.75 threshold sits between them.

Claim order follows the instruction's deliverables: complete churn sequence and
how it entered → whether what returned is what left → what each release shipped
and why the tag surface misleads → the hidden file history and the restoration
that never happened → per-item note verdicts.

**Every claim is conjunctive**, and deliberately so. There is no claim that a
single `git log` satisfies: the previous revision paid three separate claims for
the three SHAs of one chain, all of which fell out of one command, which handed a
shallow rollout a third of the reward for four tool calls. Now the whole sequence
— including the two landings a subject grep cannot separate and the removal that
never says "revert" — is one claim, and the judge's middle outcome is what absorbs
a partial sequence.

The hard claims and why a strong model drops them:

1. **The sequence is three landings and two removals** (claim 1). The second
   removal announces itself as a simplification. A model that enumerates removals
   by subject finds one cycle, concludes the feature shipped in 1.9.0 and stayed,
   and is wrong about the state of 1.11 as a result.
2. **The first landing is not on main** (claim 2). Side branch + merge `5b35d23`
   **and** both complementary history views (default path log vs first-parent).
   kimi-k3-runs-third's 0.933 answer named the merge and skipped both views.
3. **The cherry-pick trailer is false** (claim 4). This is the sharpest single
   trap in the fixture. The trailer is exactly the artefact a release engineer
   uses to establish provenance, it names the right commit, and the diffstats
   agree with it. Only a revision-to-revision diff disagrees.
4. **What matched vs what did not** (claim 5). Path-scoped max_size→min_size,
   a matched-signal (identical subjects *or* 10/0 stats), **and** the distinct
   pool blobs at each landing (`73f71e9` / `c6431cd`).
5. **The removal with no revert wording** (claim 7). Quoted reason plus
   content-identity proof (blob *or* equivalent).
6. **The third landing is a third design** (claim 8). Config-driven `warm_target()`.
7. **Release matrices** (claim 9). Pre-warm matrix with any-form vs surviving
   first-shipped, **and** jitter absent at every release tag.
8. **Tag surface + VERSION inventory** (claim 10). VERSION at every tag
   (including `pipeline-1.11-rc1` = `"1.10.0"` and `v1.10.0` = `"1.9.0"`) plus
   all three trust failures.
9. **v1.9.1 lineage** (claim 11). Fork-from-`f0a6be7` plus dual hotfix commits.
10. **Rename plain-vs-follow counts** (claim 12). **4** without follow, **6**
    with follow — kimi-k3-runs-third mentioned four and skipped the six.
11. **Fake jitter restore** (claim 13). Never in any release.
12. **Notes + negative search** (claims 14, 15): silent regression omitted;
    decoy revert requires a negative multi-writer search (only `1a581a9`
    itself) — also omitted in the 0.933 trial.

Levers used, against the conventions' list: layered defects (the divergence sits
behind the sequence, the release matrix behind the divergence, and two note
bullets behind the matrix); claims depending on quantities the prompt never
mentions (the constructor defaults, the semantic tag order, the blob identities);
cross-referencing two artefacts (the changelog against the code at a tag, six
times, in four different failure modes); decoys that survive casual checking
(three of them, in three different directions — a feature that reads as a revert,
a revert that restores nothing, a removal that reads as a cleanup); an ordering
that cannot be inferred from one computation (version sort across a non-version
tag, plus an ancestry relation that contradicts the version numbers); and
evidence that contradicts the cheapest correct-looking measurement (identical
diffstats and a provenance trailer over a real divergence).

## Realism trade

The repository is synthetic. A real service repo would have more authors, review
trailers, CI config, generated files, more merges, and a changelog maintained with
less discipline. Commit bodies here are cleaner and more informative than they
usually are, which makes the removal rationales easier to read than they would be
in practice — a deliberate concession, because a claim that depends on an
illegible commit body is a coin flip rather than a test.

What the fixture does buy is that every defect is a *pattern* rather than a quirk
of this project: a change that churns more than once, a landing that arrives by
merge, a provenance trailer that lies, two commits with one subject, a removal
that does not announce itself, a return that is a redesign, a hotfix branched
from before a feature landed, a tag cut before its version bump, a release
candidate that sorts ahead of its release, a renamed module, a revert of a revert
that restores nothing, a changelog entry contradicted by the code at its tag, a
changelog entry that is accurate but misfiled, and a changelog entry backed only
by a subject. Re-pointing at a real bundle would mean re-running the read-back
and substituting SHAs; the claim structure would not change.

## Cross-task overlap

`/data/repos/pipeline-svc` is a new path created only by this task. The task
touches no warehouse table, so there is no interaction with the eight baked
tables or with `journal-balance-forensics`'s `gl_period_close`. The git,
filesystem and code-executor allowlist overlaps other repo-analysis tasks in the
suite, which is intended.

## Tool surface

26 exposed, 8 needed, 6 same-server distractors, 12 off-server distractors —
distractor:needed ratio 18/8 = 2.25, holding the 1 same-server : 2 off-server
composition. 11 servers, 3 of them carrying needed tools. No sqlite tool is
exposed; this task has no warehouse component.

Structural friction, not a distractor: **there is no `git_tag` tool** on the git
server, and no `git_init`. That mattered before and matters more now — the tag
set, the tag *types*, `--contains`, `--follow`, `merge-base --is-ancestor` and
per-tag file reads are all reachable only through
`mcp-code-executor_execute_code` or, for the naming, through `CHANGELOG.md`,
which is the artefact the task asks the model to distrust. A model that leans on
the changelog for commit-to-release mapping inherits four of its errors.

Sharpest distractors:

- `git_git_checkout` — the mutating sibling, and now genuinely destructive to the
  analysis: it is the obvious way to "look at the code at v1.10.0", it detaches
  HEAD, and the pinned `main` is what every ancestry check is anchored to.
  `git_git_show` is the right tool and is in the needed set.
- `git_git_diff_staged` / `git_git_diff_unstaged` — the working tree is clean and
  nothing is ever staged, so both return empty forever rather than erroring.
- `calculator_calculate` — arithmetic does not order version numbers, and
  `1.10 < 1.4` numerically is the wrong answer by the same route as a lexical
  sort. It is now doubly wrong, because one tag is not a number at all.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so the reflexive
  `git log | grep -i revert` is unavailable.
- `desktop-commander_start_search` — searches file *text*. It will find the word
  "Revert" in `CHANGELOG.md` and never touch the history.
- `context7_resolve-library-id`, `whois_whois_domain`, `ddg-search_search` —
  far-field. `pipeline-svc` is not a public project.

## Not verified

- **No container was booted.** `environment/Dockerfile` was not built. Its
  `COPY`/`RUN` lines and its ten build-time assertions were validated by running
  the equivalent commands against the bundle on the authoring host, not by a
  successful `docker build`.
- **The task was not run.** No agent and no oracle execution happened, so "the
  oracle scores 1.0" is an argued property, not a measured one: every claim in
  `tests/reward.toml` was checked by hand against `solution/solve.sh` and against
  `fixtures/GROUND_TRUTH.md`, and each of the 15 has a corresponding passage in
  the oracle answer.
- **The judge was not invoked.** No OpenRouter call was made; claim wording has
  not been exercised against the configured judge. The claims are longer and more
  conjunctive than in the previous revision, which is a deliberate difficulty
  choice but also an unmeasured risk: a judge may award the middle outcome more
  often than intended simply because each claim asks for more.
- **Kimi-K3-runs-third scored 0.933 on the only completed trial** (29 calls;
  two RuntimeError truncations excluded). That answer cleared the prior hard
  obligations (landing blobs, any-vs-surviving, silent regression) but skipped
  dual history views, plain-vs-follow **6**, and the multi-writer negative
  search. Instruction+claims now require those plus VERSION-at-every-tag and a
  jitter-absent-at-every-release matrix. `tool_output_cap` raised to 400000 to
  reduce truncate-as-failure. Re-roll before treating the floor as measured.
- **`target_tool_calls = 70` is an estimate**, not a measured trajectory length,
  and it is the top of the conventional range. The honest expectation is that a
  thorough trajectory runs longer than 70: nine per-tag file reads alone are
  needed for the release matrix, before any of the ancestry, blob or diff work.
- **The MCP git server's behaviour on this repo is untested**, and this fixture
  leans on it harder than the previous one. It is assumed that `git_git_log`
  accepts a `repo_path` pointing at `/data/repos/pipeline-svc` and exposes a
  message grep, and that `git_git_show` can read `<rev>:<path>` for both
  lightweight and annotated tags. If any of that is unavailable the history is
  still fully readable through `mcp-code-executor_execute_code`, so the task
  remains solvable, but the call count rises.
- **`git` is assumed present in the base image**, since the Dockerfile clones at
  build time, and a git old enough to lack `--follow` or `merge-base
  --is-ancestor` would break two claims. Neither assumption was tested against
  the image.
