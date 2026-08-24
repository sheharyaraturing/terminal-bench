# NOTES, transitive-pin-escape

## Premise

A Build Engineer has a nightly export that has failed on every run since the
second-to-last release. Layer 1 is what a single `git log -p -- requirements.txt`
finds: somebody loosened a direct pin four weeks earlier, from `pandas==2.1.4`
to `pandas>=2.1,<3`. It is a real change, it has a plausible rationale in its
commit body, and it is not the cause.

Everything that matters sits behind it:

- pandas resolved to **2.2.2 at both** the last good release and the first
  failing one. The loosening changed what shipped one release earlier, and that
  release ran clean. Ruling it out is only possible by reading what each build
  actually resolved to, which is a different artefact from what the repository
  asks for.
- what actually moved is **botocore**, 1.34.88 to 1.35.14, a package that
  appears in neither the direct-requirements file nor the constraints file at any
  commit in the 52-commit history. It arrives through the direct requirement on
  the S3 filesystem package by way of that package's async AWS client wrapper.
- behind that, a fully resolved **lockfile was committed once and deleted
  sixteen days later**, so exactly one tagged release, v2.8.0, was ever
  genuinely protected. `git tag --contains` on the commit that *added* the file
  reports four tags, because that commit is an ancestor of all four; the file is
  present at only one of them. Containment is not presence.
- the protection lapsed at v2.9.0, one release *before* the failure surfaced,
  because v2.9.0 happened to resolve botocore to a 1.34 version anyway. That
  offset is why nobody connected the two.
- one commit in the same window is a pin edit that changes no version.

## Fixture provenance

The repository is **synthetic and authored here**. No upstream project was
cloned; nothing was downloaded.

| artefact | injected as | measured size |
|---|---|---:|
| `fixtures/metrics-etl.bundle` | `git clone` to `/data/repos/metrics-etl` | **24,467 bytes** |
| `fixtures/build_fixture.sh` | not injected, the builder | 41,027 bytes |
| `fixtures/GROUND_TRUTH.md` | not injected, authoring artefact | 13,026 bytes |

Build invocation:

```
bash environment/fixtures/build_fixture.sh
```

It was actually run. Contents: 52 commits, single linear branch, no merges, 12
tracked files at the tip (`CHANGELOG.md`, `Makefile`, `README.md`,
`build/README.md`, `build/sbom.txt`, `constraints.txt`,
`docs/incidents/2024-07-nightly-export.md`, `requirements.txt`, `src/cli.py`,
`src/frame.py`, `src/sink_s3.py`, `tests/test_frame.py`), plus
`requirements.lock` which exists only between commits 27 and 31. Eight
lightweight release tags.

**Pinned SHA**, the value in `environment/Dockerfile`:

```
6d120f7400623a25d7d5e08ff0b2dff101bf130b
```

`git cat-file -t 6d120f7400623a25d7d5e08ff0b2dff101bf130b` returns `commit` in a
fresh clone of the bundle. Every one of the eleven assertions the Dockerfile
makes was executed against such a clone and passed: `rev-parse HEAD`,
`abbrev-ref HEAD` = `main`, `rev-list --count HEAD` = 52,
`rev-list --count --merges HEAD` = 0, eight tags, twelve tracked files, non-empty
`CHANGELOG.md` and `build/sbom.txt`, no `requirements.lock` at HEAD,
`git cat-file -e v2.8.0:requirements.lock` succeeding, and the two botocore
version greps at v2.9.0 and v2.10.0.

Determinism: the script was copied **alone into an empty directory** and re-run.
Bundle checksum reproduced exactly and `GROUND_TRUTH.md` came back
byte-for-byte identical (`diff` clean):

```
metrics-etl.bundle  sha256 0199c1ea7bcbea204036d03ff240da1d6e0c50ee67f96d2971fe28a162fbf516
```

What makes that hold: `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`,
`GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` are exported once; **both**
`GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` are set on every single commit, in raw
`@<epoch> +0000` form derived arithmetically from the commit index, so no locale
or timezone can leak in; tags are **lightweight**, so no tagger identity or
tagger date enters an object hash; `git commit --no-gpg-sign` runs with a scratch
`HOME`, an empty `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM=/dev/null`, so no
ambient user config participates; and every generated file is written by an
explicit heredoc or by a loop over a fixed sorted list, no directory iteration,
no RNG, no `date`.

The bundle was created with `git bundle create metrics-etl.bundle --all`, **never `--depth 1`**, because `git_git_log` needs the whole history and the task
is entirely about history. `--all` carries `refs/tags/*`, which is how the eight
tags reach the container; confirmed by cloning and running `git tag`.

The Dockerfile uses `git checkout -B main <SHA>` rather than `-b`. The bundle
carries `HEAD`, so a clone already lands on a `main` at the right commit and `-b`
fails with "a branch named 'main' already exists". `-B` is idempotent and still
asserts the SHA.

### The artefact that makes the ground truth knowable

`build/sbom.txt` is rewritten at every release commit with the dependency set
that release *actually resolved to*, in pip-compile shape, each package annotated
with its resolution parents (`# via aiobotocore` / `# via s3fs`).
`build/README.md` states in the repository that it is written by the release job
after install and that **nothing installs from it**. That distinction is the
whole mechanism: `requirements.txt` and `constraints.txt` record what was asked
for, `build/sbom.txt` records what arrived, and a transitive package can move
without either input file changing.

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, and generated from the
bundle rather than from the builder's working tree. The read-back stage clones
`metrics-etl.bundle` into a scratch directory, checks out the pinned SHA as
`main`, and then runs the commands an agent would run: `git log`, `git log
--grep`, `git log --diff-filter=AD`, `git show`, `git show --numstat`,
`git cat-file -e`, `git tag --contains`, `sort -V`. Whatever those print is the
file.

The pin comparison specifically is done by **independent code**, not by trusting
the version tables in the build script: a small Python script re-parses
`build/sbom.txt` out of each tag with a regex and diffs the two dictionaries.
That is what produced "exactly four packages moved".

Read-back facts, all of which appear in `tests/reward.toml`:

| short SHA | role | date |
|---|---|---|
| `6d120f7` | HEAD / pinned branch tip | 2024-07-30 |
| `aa730ca` | Layer 1: `deps: loosen the pandas pin` | 2024-05-19 |
| `d85a5a8` | decoy: `deps: tidy up constraints.txt` | 2024-05-15 |
| `2e8bfe9` | lockfile added | 2024-04-21 |
| `b512dac` | lockfile deleted | 2024-05-07 |
| `3056ccb` | the incident record | 2024-07-06 |
| `aeba6ea` | `v2.9.0`, last clean release | 2024-06-04 |
| `da8975c` | `v2.10.0`, first failing release | 2024-06-28 |

and:

- 19 packages recorded at both v2.9.0 and v2.10.0; none added, none removed;
  **exactly four** version changes, `botocore 1.34.88 -> 1.35.14`,
  `certifi 2024.2.2 -> 2024.7.4`, `charset-normalizer 3.3.2 -> 3.3.4`,
  `idna 3.6 -> 3.7`. For contrast v2.8.0 to v2.9.0 has eight movers (including
  pandas) and broke nothing, and v2.10.0 to v2.11.0 has six.
- `pandas==2.2.2` at v2.9.0, v2.10.0 and v2.11.0; `pandas==2.1.4` at v2.4.0
  through v2.8.0.
- botocore across the eight releases: 1.34.34, 1.34.39, 1.34.44, 1.34.48,
  1.34.51, 1.34.88, 1.35.14, 1.35.29.
- botocore appears **0 times** across every revision of `requirements.txt` and
  `constraints.txt` in the whole history (checked by iterating `git rev-list HEAD`
  and grepping both blobs at each commit).
- 5 direct requirements and 4 constraint entries at HEAD; 19 hard pins in
  `requirements.lock`, `botocore==1.34.51` among them.
- `requirements.lock` present at v2.8.0 and absent at all seven other tags
  (`git cat-file -e <tag>:requirements.lock`), while
  `git tag --contains 2e8bfe9` reports four tags.
- `git diff v2.9.0 v2.10.0 -- requirements.txt constraints.txt` is empty.
- decoy `--numstat` is `9 4 constraints.txt`; the constraint set reduced to
  name==version with whitespace stripped is identical before and after.
- `git tag` default order is lexical: `v2.10.0 v2.11.0 v2.4.0 ...`.
  `git tag --contains aa730ca` prints `v2.10.0, v2.11.0, v2.9.0`.

Read-back caught three things the first build did not get right, all fixed and
the bundle rebuilt (which is why the SHAs here are not the first run's):
`requirements.txt` pinned `pyarrow==15.0.2` at v2.4.0 while the recorded set said
`14.0.2`, an outright contradiction of a hard pin; the `CHANGELOG.md` release
dates did not match the tag commit dates; and the incident file was named
`2024-08-...` while it was committed on 2024-07-06. Each was found by re-reading
the built artefact, not by reviewing the script. A separate independent check
walked all eight tags and confirmed that every `==` pin in `requirements.txt` and
`constraints.txt` agrees with the recorded set at that tag.

## Difficulty design

Claim order is Layer 1  to  Layer 2  to  decoy. A model that stops at Layer 1 banks
the early claims and drops the later ones.

15 claims, every one at the default weight of 1.0. Dropping three gives
12/15 = **0.80**; dropping four gives 11/15 = **0.733**. The 0.75 threshold sits
between them.

**Three claims were added after GLM-5.3 scored 0.82 / 0.75 / 0.68 on
job-99fba809.** Two of them require chaining rather than looking up: the path by
which botocore reaches the build is three hops, s3fs to aiobotocore to botocore,
and no single file states it; and the conclusion that every hand-maintained pin
held its version across the boundary needs both sides of two packages read and
compared before the "nothing we pinned could have caught this" inference lands.

**A fourth was added after job-5561b8a3 (0.9333 / 1.0 / 0.9333).** The cascade
claim scored 1.0 in all three trials there, because the model happened to read
the locked version correctly; cascading only pays when the base is reliably
wrong, which this one was not. The trajectory showed the real ceiling instead:
the repository is 9.7 KB across 12 files, so the model reads all of it in about
six calls, and `docs/incidents/` hands over the framing by ruling out the input
data, the code, the credentials and pyarrow before the model starts.

Rather than delete that write-up, which is a realistic artefact and grounds the
symptom, the task now scores the fact that it is **wrong**. It claims the upload
code has not been touched since 2.8.0; `src/sink_s3.py` was in fact changed at
527ec56 on 2024-07-10. That contradiction already existed in the fixture and was
unscored. It is a genuine trap rather than a gotcha: the commit adds six lines
and removes none, wrapping the failing call to re-raise a legible error, changes
no behaviour, is never called, and is carried by v2.11.0 alone, so it cannot be
the cause. A model that trusts the write-up misses it; a model that checks it
and then over-corrects into blaming that commit is also wrong.

The third is deliberately **built on a claim the model already gets wrong**. One
trial reported the lockfile's botocore pin as 1.34.88, which is the version
resolved at the following release, rather than 1.34.51. The new claim derives
from that value: 1.34.51 is exactly what v2.8.0 installed, so the lockfile froze
botocore where it already stood, and had it survived botocore could not have
reached the failing 1.35.14. A model that gets the base value wrong cannot reach
the derived conclusion, so one error costs two claims instead of half of one.

**The claim asserting the history is 52 linear commits was removed**: the prompt
never asks how large or what shape the history is, so it scored a constraint
nobody requested. Two others were relaxed for the same reason. The rationale
behind the loosened pin now accepts any faithful rendering, and the lockfile
claim no longer requires both SHAs, both dates and the count of 19 pins, since
the prompt asks only whether protection existed and when it lapsed.

**The arbitrary-code tools were removed.** `mcp-code-executor_execute_code` and
`mcp-server-code-runner_run-code` were exposed on the reasoning that the executor
was the only route to the tag set. On the sibling task `revert-reland-divergence`
that reasoning proved wrong: the executor is a route to all of git, and GLM-5.3
looped over every tag inside a single call. Both routes this task needs were
verified reachable without them, `git tag --contains` through
`cli-mcp-server_run_command` and the two recorded dependency sets through two
`git_git_show` calls compared in context.

The load-bearing claims and why a strong model drops them:

1. **The loosened pandas pin is a red herring** (claim 8). The prompt itself
   points at it, the commit body is persuasive, and it is the only declared
   version change in the window. Ruling it out requires realising that "what we
   asked for" and "what got installed" are different artefacts, then reading the
   second one at two tags. A model that stops when it finds a loosened pin
   produces a confident, coherent, wrong answer.
2. **botocore 1.34.88  to  1.35.14 is the cause** (claim 9). Four packages move
   across the boundary. Picking the right one needs the resolution parents joined
   to the failing call site, the sink imports the S3 filesystem package and
   calls the AWS client's multipart completion, so only the AWS client's supplier
   is on that path.
3. **botocore is transitive and pinned nowhere** (claim 10). The insight the task
   is named for. It requires actively confirming a negative, that a package name
   appears in neither input file at any commit, which models tend to assert
   loosely rather than establish.
4. **First shipped in v2.9.0, not v2.10.0** (claim 11). There is no `git_tag`
   tool, so the tag set has to come through the code executor; and the obvious
   command's first line is the wrong answer, because `2.10.0` sorts lexically
   before `2.4.0`. `calculator_calculate` is exposed and will confirm the wrong
   answer, since 2.10 < 2.4 numerically too.
5. **The lockfile existed and was deleted** (claim 12). Only visible if the model
   keeps going after it has a cause. `git log -- requirements.lock` finds it
   instantly, but nothing in the prompt or in the changelog suggests looking:
   the 2.8.0 changelog section advertises the lockfile and no later section
   mentions its removal.
6. **Exactly one release was protected** (claim 13). The sharpest claim. The
   natural command, `git tag --contains <add-SHA>`, returns four tags and is
   *correct about containment and wrong about the question*. Getting one requires
   checking file presence per tag instead. A model that answers "four" has done
   real work and still failed.
7. **The protection lapsed one release before the failure** (claim 14). Requires noticing that v2.9.0 shipped
   unprotected and still worked. Models compress "when did it break" and "when
   did it become possible for it to break" into one date.
8. **The decoy** (claim 15). `git log -- constraints.txt` returns two commits
   in the window; one is a 9-insertion, 4-deletion edit to a pin file four days
   before the real one, with a body about holding a version back. It survives
   every casual check, right file, right vocabulary, real diff, and changes no
   version. Detecting that needs the before/after sets normalised for whitespace
   and ordering.

Levers used, against the conventions' list: layered defects (1, the transitive
mover sits behind the red herring and the lockfile sits behind the mover), a
claim depending on a quantity the prompt never mentions (2, the semantic tag
order and the per-tag file presence), cross-referencing two artefacts (3, the
declared pins against the recorded resolution, and the incident note against the
tag order), a decoy that survives casual checking (4), and a direction that
cannot be inferred from one computation (5, that protection lapsed one release
before the symptom, not at it).

Deliberately *not* used as difficulty: vagueness. The prompt asks for every piece
of the deliverable, though after the hand-holding trim it does so through Nadia's
goals rather than a numbered list: what moved, how it got in, why nothing held
it, whether any release was protected and which, what the pin was taken off for
and how that work has behaved, the dependency commits ruled in or out by name,
and what would have prevented it. What it never says is how to find any of it.

A QC pass against rubric v1.1 (qa/reports/transitive-pin-escape-v2-2026-08-23.xlsx)
found three claims stranded by that trim, scoring asks the prompt no longer made.
Explicit asks were restored for all three, and the next rollout showed that was
the wrong fix: C8, C9 and C15 all went to 1.0 in six of six trials, and C9 in
particular went from 0.25 to 1.0. The restored sentences did not ground those
claims, they handed them over. C9's read "what it was taken off for and whether
that work has behaved since", which names both halves of what the claim scores.

Two of those three sentences have been removed again, deliberately, with the E15
gap accepted rather than closed by hinting. The pin's purpose now rests on the
argument having to be "made properly or killed properly", which cannot be settled
by version equality alone, and the inert commit on "commits in that window I
could not account for either way", which states the frustration symmetrically and
never suggests one is inert.

The remediation ask was restored, one of three rather than all three, so that a
partial pass stays reachable. It reads "Close on what we change so this cannot
happen again; the board will not let a post-mortem end without that." It asks for
a remediation without naming one: the claim wants botocore pinned by name or the
lockfile restored, and the sentence says neither. It was chosen over the other
two on evidence. Its claim scored 4/6 before any ask existed, so models were
already close to volunteering it, which makes it the cheapest of the three in
D15 terms. The pin-purpose ask was the most expensive, taking its claim from
0.25 to 1.0, and the inert-commit claim was already at 5/6 without help.

That is a real trade and it is recorded here so a later QC pass reads it as a
decision rather than as the same defect recurring. The task is meant to break
models, not to be passed; the line held is that every claim stays reachable from
a goal. If C9 comes back at 0.0 across a whole cohort it is unreachable rather
than hard, and the honest response then is to drop the claim, not to re-add the
sentence that made it free.

Only the fourth ask survives, "if we were, tell me which releases those were".
It asks whether and which without naming v2.8.0, and it is the one restore whose
claim did not collapse: C12 scored 0.75.

## Tool surface

26 exposed, 8 needed, 6 same-server distractors, 12 off-server distractors, distractor:needed ratio 18/8 = 2.25, holding the 1 same-server : 2 off-server
composition. 10 servers, 3 of them carrying needed tools. Every declared server
carries at least one allowlisted tool and every allowlisted tool's server is
declared. `sqlite_delete_records` is not exposed; no sqlite tool is, because this
task has no warehouse component.

Structural friction, not a distractor: **there is no `git_tag` tool** on the git
server and no `git_init`. The tag set is reachable only through
`mcp-code-executor_execute_code` (or inferred from `CHANGELOG.md`), and the task
turns on the tag set's *semantic* order. Comparing two recorded dependency sets
package by package also effectively requires the code executor, since the
crippled shell cannot pipe.

Sharpest distractors:

- `calculator_calculate`, the trap that actively produces the wrong answer.
  Feeding version strings to arithmetic gives 2.10 < 2.4, which agrees with the
  lexical sort and disagrees with reality.
- `git_git_checkout`, the mutating sibling. It is the obvious way to "look at
  the files at v2.9.0", and using it detaches HEAD and loses the pinned `main`
  the analysis is anchored to. `git_git_show` is the right tool and is in the
  needed set.
- `git_git_diff_staged` / `git_git_diff_unstaged`, near-misses on the tool a
  model actually wants. The tree is always clean and nothing is ever staged, so
  both return empty forever; a model reaching for them to compare two tags gets
  silence rather than an error.
- `cli-mcp-server_run_command`, no pipes and `/data` only, so the reflexive
  `git log -p -- requirements.txt | grep pandas` is unavailable.
- `desktop-commander_start_search`, searches file *text*. It will find the word
  "botocore" in `build/sbom.txt` at HEAD and never establish that no input file
  ever names it, which is the actual claim.
- `context7_resolve-library-id` and `context7_query-docs`, the most tempting
  far-field pair in the set. Looking botocore up in third-party documentation
  feels like the way to explain a checksum keyword, and it cannot tell you what
  *this* repository resolved to. There is no egress in the task image either.
- `ddg-search_search`, `whois_whois_domain`, far-field. `metrics-etl` is not a
  public project.

## Realism trade

The repository is synthetic. A real build repo of 52 commits would have merges,
multiple authors, CI configuration, review trailers, and a changelog kept with
less discipline than this one. Two concessions in particular are deliberate:
commit bodies here are cleaner and more informative than they usually are,
because a claim resting on an illegible commit body is a coin flip rather than a
test; and `build/sbom.txt` being rewritten at exactly every release commit is
tidier than most release jobs manage. The underlying artefact is real practice, teams do commit post-install resolution snapshots for audit, but real ones are
patchier.

The trade buys full knowability: every SHA, package name and version in the
claims came out of the built bundle, read back by independent code. The claim
structure would survive swapping in a real repository, because each claim
describes a *pattern* rather than this project, a direct pin loosened for a
plausible reason and irrelevant to the outcome, a breaking version arriving
through an unpinned transitive edge, a lockfile whose lifetime spans exactly one
release, containment-of-commit mistaken for presence-of-file, a lexical-versus-
semantic tag ordering, and a pin-file edit that moves no version. A re-point
would mean re-running the read-back stage and substituting SHAs and versions; the
phase chain and the weighting would not change.

## Cross-task overlap

`/data/repos/metrics-etl` is a new path created only by this task; it does not
collide with `revert-reland-divergence`'s `/data/repos/pipeline-svc`. The task
touches no warehouse table, so there is no interaction with the eight baked
tables or with the extra tables other tasks in the batch create. The git,
filesystem and code-executor allowlist overlaps `revert-reland-divergence`, which
is intended, the same toolchain, a different defect class, and the tag-ordering
trap is exercised on a different quantity (which release *carries a file* rather
than which release *first contains a commit*).

## Not verified

- **No container was booted.** `environment/Dockerfile` was not built. Its
  `COPY`/`RUN` lines were validated by running the equivalent commands against
  the bundle on the authoring host, all eleven build-time assertions were
  executed against a fresh clone and passed, but not by a successful
  `docker build`.
- **The task was not run.** No agent and no oracle execution happened, so "the
  oracle scores 1.0" is an argued property, not a measured one: every claim in
  `tests/reward.toml` was checked by hand against `solution/solve.sh` and against
  `fixtures/GROUND_TRUTH.md`, and each of the 15 has a corresponding passage in
  the oracle answer.
- **The judge was not invoked.** No OpenRouter call was made; claim wording has
  not been exercised against `openrouter/anthropic/claude-sonnet-5`.
- **The difficulty target is design intent, not measurement.** No Kimi-K3 or
  GLM5.3 rollout was performed. The claim that those models land a partial pass
  rests on the weighting arithmetic above and on the argument for each weighted
  claim, not on observed coverage.
- **`target_tool_calls = 27` is measured**, not an estimate. Six trials on sha
  fb6cf35 took 17, 27, 27, 27, 32 and 8 calls. The value has been wrong twice
  before, at 64 and then 48, both walk-throughs that the runs did not bear out.
- **The MCP git server's behaviour on this repo is untested.** In particular it
  is assumed that `git_git_log` accepts a `repo_path` argument pointing at
  `/data/repos/metrics-etl` (the server is declared with no `--repository` pin),
  and that `git_git_show` can be given a `<rev>:<path>` argument. If it cannot,
  the history is still fully readable through
  `mcp-code-executor_execute_code`, so the task remains solvable, but the
  expected call count would rise.
- **`git` is assumed present in the base image**, since the Dockerfile clones at
  build time. The template's own comment block documents this injection route,
  but the assumption was not tested against the image.
- **The botocore failure mode is plausible, not researched.** A 1.34-to-1.35
  minor bump sending a checksum keyword an older client did not accept is
  modelled on real behaviour in that library's history, but no upstream changelog
  was consulted, there is no egress. Nothing in the claims depends on the real
  library: every version number is a property of the authored fixture.
