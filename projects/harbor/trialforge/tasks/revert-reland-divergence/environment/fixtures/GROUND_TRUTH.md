# GROUND_TRUTH.md — revert-reland-divergence

Everything below is the **output of git commands run against a fresh clone of
`pipeline-svc.bundle`**, not against the builder's working tree. `bash
build_fixture.sh` rebuilds the bundle and regenerates this file; the SHAs below
are therefore the SHAs an agent will see.

Read-back procedure:

```
git clone pipeline-svc.bundle readback
cd readback && git checkout -B main aa86ca39961cd50b84023a9002fc38a6ac1054ba
```

## Shape of the repository

- pinned branch tip (the SHA `environment/Dockerfile` checks out as `main`):
  `aa86ca39961cd50b84023a9002fc38a6ac1054ba`
- `git cat-file -t aa86ca39961cd50b84023a9002fc38a6ac1054ba` in the clone -> `commit`
- `git rev-list --count HEAD` -> **56** commits
- `git rev-list --count --merges HEAD` -> **1** merge commit
- `git rev-list --count --first-parent HEAD` -> **55**, so
  1 commit(s) are reachable only off the first-parent line
- `git rev-list --count --all` -> **59** (the unmerged hotfix branch adds commits
  that `HEAD` cannot see)
- branches in the clone: main origin/HEAD origin/feature/prewarm origin/hotfix/1.9.1 origin/main 
- tracked files at HEAD (10):
  - `CHANGELOG.md`
  - `README.md`
  - `docs/runbook.md`
  - `src/api.py`
  - `src/backoff.py`
  - `src/config.py`
  - `src/pool.py`
  - `src/shard.py`
  - `tests/test_backoff.py`
  - `tests/test_pool.py`
- authors: Aiko Tanabe; Marcus Lindqvist; Priya Raghunathan; 
- one commit's author is not its committer:
  `5b99564  Priya Raghunathan/Marcus Lindqvist`
- first commit 2024-01-08, last commit 2024-06-30

### Tags

`git tag` (git's own default ordering — lexical, and one tag is not a version):

```
pipeline-1.11-rc1
v1.10.0
v1.11.0
v1.4.0
v1.5.0
v1.6.0
v1.7.0
v1.8.0
v1.9.0
v1.9.1
```

`git tag | sort -V`:

```
pipeline-1.11-rc1
v1.4.0
v1.5.0
v1.6.0
v1.7.0
v1.8.0
v1.9.0
v1.9.1
v1.10.0
v1.11.0
```

Tag types and targets:

  - `pipeline-1.11-rc1` -> commit object, commit `842f2d332eb7`, VERSION at that tag = "1.10.0", subject: docs: runbook note on single-writer archival
  - `v1.4.0` -> commit object, commit `81c270d4cf5b`, VERSION at that tag = "1.4.0", subject: release: 1.4.0
  - `v1.5.0` -> commit object, commit `00e33aee72e7`, VERSION at that tag = "1.5.0", subject: release: 1.5.0
  - `v1.6.0` -> commit object, commit `26dd7653b3c2`, VERSION at that tag = "1.6.0", subject: release: 1.6.0
  - `v1.7.0` -> commit object, commit `29f455c72435`, VERSION at that tag = "1.7.0", subject: release: 1.7.0
  - `v1.8.0` -> commit object, commit `fe6131e1a493`, VERSION at that tag = "1.8.0", subject: release: 1.8.0
  - `v1.9.0` -> commit object, commit `4f91f5df0a28`, VERSION at that tag = "1.9.0", subject: release: 1.9.0
  - `v1.9.1` -> commit object, commit `8cdab8ef5c99`, VERSION at that tag = "1.9.1", subject: release: 1.9.1
  - `v1.10.0` -> tag object, commit `c62e5a513b84`, VERSION at that tag = "1.9.0", subject: docs: changelog for 1.10.0
  - `v1.11.0` -> tag object, commit `6d92d0d5b5a8`, VERSION at that tag = "1.11.0", subject: release: 1.11.0

**`v1.10.0` and `v1.11.0` are annotated tags; the rest are lightweight.**
Note the `VERSION` column: at `v1.10.0` the tagged tree still says
"1.9.0", because the tag was cut before the version bump commit
`03a1d467f627`.

## Every commit whose subject mentions a revert

`git log --all --format='%h %ad %s' --date=short --grep='[Rr]evert'`:

```
1a581a9 2024-06-09 Revert to a single writer per shard
c5e2305 2024-05-13 Revert "Revert \"Add jittered exponential backoff to the retry loop\""
121e367 2024-05-10 Revert "Add jittered exponential backoff to the retry loop"
f0a6be7 2024-03-26 Revert "Pre-warm the connection pool on worker start"
```

Of those, the ones that actually remove the thing their subject names:
`f0a6be719e1d` and `121e3672ca26`. The other two are traps.
And the pre-warm's **second** removal, `de96d2801b6f`, does not appear in this
list at all, because its subject never says "revert".

## Layer 1 — the pre-warm churns three times, not once

`git log --format='%h %ad %s' --date=short -- src/pool.py`:

```
77b8763 2024-05-31 pool: warm the pool to the configured target
de96d28 2024-05-22 pool: simplify worker start-up
5b99564 2024-04-07 Pre-warm the connection pool on worker start
f0a6be7 2024-03-26 Revert "Pre-warm the connection pool on worker start"
9d8b9f6 2024-03-11 Pre-warm the connection pool on worker start
2e026fc 2024-01-17 pool: bound lock acquisition with acquire_timeout
c10f91d 2024-01-08 Initial import of pipeline-svc
```

| step | role | full SHA | short | date | author |
|---|---|---|---|---|---|
| 1 | first landing (on a side branch) | `9d8b9f69017f49053c253972c644ac0ee325ac71` | `9d8b9f69017f` | 2024-03-11 | Marcus Lindqvist |
| 2 | merge that brought it to main | `5b35d23fd6fdc7f5c2136e355159b7131c4426a1` | `5b35d23fd6fd` | 2024-03-17 | Priya Raghunathan |
| 3 | first removal (a true revert) | `f0a6be719e1d3118afbb94c6383ef7bd5d054018` | `f0a6be719e1d` | 2024-03-26 | Priya Raghunathan |
| 4 | second landing (claims to be a cherry-pick) | `5b995647c56801bc777a66f589d340d99f4ca46b` | `5b995647c568` | 2024-04-07 | Priya Raghunathan |
| 5 | second removal (subject says nothing) | `de96d2801b6faafed12ba9aaa17f0b826d2f7f7b` | `de96d2801b6f` | 2024-05-22 | Aiko Tanabe |
| 6 | third landing (a different design) | `77b87636a12c8dbd4b1d97a3d0324b7ca73f649a` | `77b87636a12c` | 2024-05-31 | Marcus Lindqvist |

### The first landing is not on the first-parent line

- `git merge-base --is-ancestor 9d8b9f69017f HEAD` -> ancestor: yes
- `git rev-list --first-parent HEAD | grep -c 9d8b9f69017f` -> 0
- parents of the merge `5b35d23fd6fd`: a1868cd 9d8b9f6
- `git log --oneline --first-parent -- src/pool.py` (what a first-parent read shows):

```
77b8763 pool: warm the pool to the configured target
de96d28 pool: simplify worker start-up
5b99564 Pre-warm the connection pool on worker start
f0a6be7 Revert "Pre-warm the connection pool on worker start"
5b35d23 Merge branch 'feature/prewarm' into main
2e026fc pool: bound lock acquisition with acquire_timeout
c10f91d Initial import of pipeline-svc
```

Neither of the two obvious views is complete. The default
`git log -- src/pool.py` lists the side-branch landing `9d8b9f69017f` but **not** the
merge `5b35d23fd6fd` — history simplification drops a merge that is TREESAME to a
parent — while `--first-parent` lists the merge but **not** the landing. The
sequence is only complete if both are read.

The history also carries one empty commit, which has no diff at all:

```
9a4882f 2024-06-06 chore: retrigger the release pipeline -> changed paths: 0
```

### Recorded reason for the first removal

`git log -1 --format='%b' f0a6be719e1d`:

```
This reverts the pre-warm change. On the deploy that carried it every worker
opened its full ceiling of connections simultaneously and we tripped the
upstream connection limit inside forty seconds. Reverting to unblock the
release; we will bring it back once the warm target is sane.
```

It is a genuine back-out, checked by content and not by the subject:
`src/pool.py` at the removal versus at the parent of the first landing —
`a2d81b37f2dd` vs `a2d81b37f2dd` -> IDENTICAL

## Layer 2 — the second landing lies about being a cherry-pick

Body of `5b995647c568`:

```
Rolling this forward again for the 1.9 cycle now that there is a warm-target
knob to hang it off.

(cherry picked from commit 9d8b9f69017f49053c253972c644ac0ee325ac71)
```

The trailer names `9d8b9f69017f`. The two are not the same change:

`git diff 9d8b9f69017f 5b995647c568 -- src/pool.py`:

```
diff --git a/src/pool.py b/src/pool.py
index 73f71e9..c6431cd 100644
--- a/src/pool.py
+++ b/src/pool.py
@@ -43,4 +43,4 @@ class ConnectionPool:
                 self._idle.append(self.factory())
 
     def start(self):
-        self._prewarm(self.max_size)
+        self._prewarm(self.min_size)
```

- path-scoped `--numstat`: `1	1	src/pool.py`
- whole-tree `--shortstat` between the same two commits:
  `6 files changed, 20 insertions(+), 2 deletions(-)`
- pool blobs: `73f71e95ae12` at the first landing,
  `c6431cdfcc58` at the second

### Neither the subject nor the diffstat separates them

- both subjects are byte-identical:
  `Pre-warm the connection pool on worker start`
- `git log --all --format='%h %an %s' --grep='^Pre-warm the connection pool on worker start$'`:

```
5b99564 Priya Raghunathan Pre-warm the connection pool on worker start
9d8b9f6 Marcus Lindqvist Pre-warm the connection pool on worker start
```

- each commit read on its own:

```
9d8b9f6 Pre-warm the connection pool on worker start
10	0	src/pool.py
5b99564 Pre-warm the connection pool on worker start
10	0	src/pool.py
```

  Both are **10 insertions, 0 deletions in `src/pool.py` and nothing else**.

### The numbers the difference has to be read against

```
  9:    def __init__(self, factory, min_size=2, max_size=32, acquire_timeout=5.0):
```

`max_size` is 32 and `min_size` is 2, and `245abbe660de`
(2024-04-04, "config: add a pool warm target knob") had added
`POOL_WARM_TARGET = "min"` immediately before the second landing.

## Layer 3 — the second removal never says "revert"

`git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short de96d2801b6f`:

```
de96d2801b6faafed12ba9aaa17f0b826d2f7f7b
Aiko Tanabe
2024-05-22
pool: simplify worker start-up

Worker start-up has accumulated more moving parts than it needs. Take the
start-up path back to the plain constructor and let the pool fill on demand.


 src/pool.py | 10 ----------
 1 file changed, 10 deletions(-)
```

- `git diff --numstat de96d2801b6f^ de96d2801b6f` -> `0	10	src/pool.py`
- it deletes `_prewarm()` and `start()`: `grep -c 'def start'` on `src/pool.py` goes
  from 1 at its parent to 0 at the commit
- the pool module lands back on the blob it had before the second landing:
  `a2d81b37f2dd` vs `a2d81b37f2dd` -> IDENTICAL

## Layer 4 — the third landing is a third design

`git show --format='%b' --stat 77b87636a12c`:

```
Bring the warm-up back, driven by POOL_WARM_TARGET rather than a hard-coded
bound, so the ceiling case that broke us earlier in the cycle cannot be
selected by accident.


 src/pool.py | 20 ++++++++++++++++++++
 1 file changed, 20 insertions(+)
```

`git diff 5b995647c568 77b87636a12c -- src/pool.py`:

```
diff --git a/src/pool.py b/src/pool.py
index c6431cd..8291248 100644
--- a/src/pool.py
+++ b/src/pool.py
@@ -42,5 +42,15 @@ class ConnectionPool:
             while len(self._idle) < count:
                 self._idle.append(self.factory())
 
+    def warm_target(self):
+        """Resolve the configured warm target to a connection count."""
+        from src.config import POOL_WARM_TARGET
+
+        if POOL_WARM_TARGET == "max":
+            return self.max_size
+        if POOL_WARM_TARGET == "off":
+            return 0
+        return self.min_size
+
     def start(self):
-        self._prewarm(self.min_size)
+        self._prewarm(self.warm_target())
```

The argument handed to `_prewarm` at each landing:

- 9d8b9f69017f -> `self.max_size`
- 5b995647c568 -> `self.min_size`
- 77b87636a12c -> `self.warm_target()`, resolved by a new `warm_target()` method
  that reads `POOL_WARM_TARGET` and can also select `max_size` or 0

So no two of the three landings are the same change, and the survivor is the
only one that is configuration-driven.

## Layer 5 — which releases actually shipped a pre-warm

`grep -c 'def start' src/pool.py` at each tag, in semantic order:

  - `pipeline-1.11-rc1` -> 1, warms `self.warm_target()`
  - `v1.4.0` -> 0
  - `v1.5.0` -> 0
  - `v1.6.0` -> 0
  - `v1.7.0` -> 0
  - `v1.8.0` -> 0
  - `v1.9.0` -> 1, warms `self.min_size`
  - `v1.9.1` -> 0
  - `v1.10.0` -> 0
  - `v1.11.0` -> 1, warms `self.warm_target()`

- `git tag --contains 5b995647c568` -> `pipeline-1.11-rc1 v1.10.0 v1.11.0 v1.9.0 `
- `git tag --contains 77b87636a12c` -> `pipeline-1.11-rc1 v1.11.0 `
- `git tag --contains 9d8b9f69017f` -> `pipeline-1.11-rc1 v1.10.0 v1.11.0 v1.8.0 v1.9.0 v1.9.1 `

**Commit containment is not release presence.** `9d8b9f69017f` is an ancestor of
`v1.8.0` and `v1.9.1`, so `git tag --contains` lists both, yet `grep -c 'def start'`
on `src/pool.py` is 0 at `v1.8.0` and 0 at `v1.9.1`: the commit is reachable and its
effect is not, because the removal is reachable too. A model that answers this
question with `--contains` alone gets it wrong in both directions.

Read carefully: the pre-warm shipped in **v1.9.0**, was **absent again in
v1.10.0** because `de96d2801b6f` removed it before that tag was cut, and came back
in **v1.11.0** in its third form. "First shipped in v1.9.0 and present ever
since" is false. The earliest tag containing the surviving implementation is
`pipeline-1.11-rc1` by `sort -V`, which is a release *candidate* tag and not a
release; the first release carrying it is `v1.11.0`.

### v1.9.1 is not a descendant of v1.9.0

- `git merge-base --is-ancestor v1.9.0 v1.9.1` -> no
- `git merge-base --is-ancestor 5b995647c568 v1.9.1` -> no
- the hotfix branch was cut from `f0a6be719e1d`, the first removal, so it never carried a
  pre-warm at all: `grep -c 'def start'` at `v1.9.1` -> 0
- `git log --oneline v1.9.0..v1.9.1` (what 1.9.1 has that 1.9.0 does not):

```
8cdab8e release: 1.9.1
963582c docs: changelog for 1.9.1
5f72d7d shard: guard against an empty routing table
```

- `git log --oneline v1.9.1..v1.9.0` (what 1.9.1 is missing):

```
4f91f5d release: 1.9.0
391476b docs: changelog for 1.9.0
e99f0af tests: cover the warm pool on start-up
5b99564 Pre-warm the connection pool on worker start
245abbe config: add a pool warm target knob
fe6131e release: 1.8.0
f240eaa docs: changelog for 1.8.0
```

The same hotfix exists twice, as two different commits: `5f72d7d928c4` on the
branch and `3a3a3d0e6c5f` on main, same subject
("shard: guard against an empty routing table"), and the second carries a
faithful cherry-pick trailer naming the first.

## Layer 6 — the backoff policy was renamed, then churned

`git log --format='%h %ad %s' --date=short -- src/backoff.py` (no `--follow`):

```
c5e2305 2024-05-13 Revert "Revert \"Add jittered exponential backoff to the retry loop\""
121e367 2024-05-10 Revert "Add jittered exponential backoff to the retry loop"
751bf03 2024-05-07 Add jittered exponential backoff to the retry loop
7cb3e9e 2024-05-01 retry: move the backoff policy to src/backoff.py
```

`git log --follow --format='%h %ad %s' --date=short -- src/backoff.py`:

```
c5e2305 2024-05-13 Revert "Revert \"Add jittered exponential backoff to the retry loop\""
121e367 2024-05-10 Revert "Add jittered exponential backoff to the retry loop"
751bf03 2024-05-07 Add jittered exponential backoff to the retry loop
7cb3e9e 2024-05-01 retry: move the backoff policy to src/backoff.py
0d83736 2024-01-29 retry: cap the computed delay at max_delay
c10f91d 2024-01-08 Initial import of pipeline-svc
```

The rename is `7cb3e9ec9742` ("retry: move the backoff policy to src/backoff.py"), and
`git show --stat` on it reports a pure rename:

```
 src/{retry.py => backoff.py} | 0
 1 file changed, 0 insertions(+), 0 deletions(-)
```

| role | full SHA | short | date | author |
|---|---|---|---|---|
| jitter landed | `751bf0341da0f42a5bd67a09bd20745feb2c428d` | `751bf0341da0` | 2024-05-07 | Marcus Lindqvist |
| jitter removed | `121e3672ca266afb9c42853595b6f708867e88e9` | `121e3672ca26` | 2024-05-10 | Priya Raghunathan |
| "brought back" | `c5e2305518937611b429a8982fbfd4d2da9259f2` | `c5e230551893` | 2024-05-13 | Marcus Lindqvist |

Removal reason (`121e3672ca26`):

```
This reverts the jitter change. The replay harness is seeded and asserts
exact delays, so a non-deterministic delay_for() makes the whole suite flap.
Reverting for now; needs an injectable random source before it can go back in.
```

### The double-revert restores nothing

Subject of `c5e230551893`:

```
Revert "Revert \"Add jittered exponential backoff to the retry loop\""

Bringing the jitter change back for the 1.10 cycle now that the harness can
inject its own clock.
```

`git show --format='' c5e230551893`:

```
diff --git a/src/backoff.py b/src/backoff.py
index bf6f257..8c19518 100644
--- a/src/backoff.py
+++ b/src/backoff.py
@@ -8,6 +8,8 @@ class RetryPolicy:
         self.max_delay = max_delay
 
     def delay_for(self, attempt):
+        # Jitter needs an injectable clock before it can come back; the replay
+        # harness asserts exact delays and a seeded source is not wired up yet.
         base = self.base_delay * (2 ** attempt)
         return min(self.max_delay, base)
 
```

- `grep -c random` on the backoff module: 2 at `751bf0341da0`,
  0 at `121e3672ca26`,
  0 at `c5e230551893` — the "revert of the revert" adds none
- at the tags: v1.10.0 -> 0, v1.11.0 -> 0, HEAD -> 0
- the delay computation at HEAD is the pre-jitter one. Everything the module
  gained since the jitter left is comment text:
  `git diff --numstat 156d6dab3378 HEAD -- src/backoff.py` -> `2	0	src/backoff.py`, and
  the inserted lines are

```
  +        # Jitter needs an injectable clock before it can come back; the replay
  +        # harness asserts exact delays and a seeded source is not wired up yet.
```

- blobs: `8c19518885b5` at HEAD versus `bf6f257eca2e` before the jitter landed,
  and `bf6f257eca2e` at the removal — the removal restored the pre-jitter blob
  exactly (IDENTICAL), and only the double-revert's comment moved it since

## Layer 7 — the draft notes against the tagged trees

The 1.10.0 section of `CHANGELOG.md` at HEAD:

```
## 1.10.0

- Jittered exponential backoff in the retry loop, which removes the
  thundering-herd spike we saw whenever an upstream came back.
- The connection pool warms to the configured target on worker start.
- Config loader accepts a per-environment override file.
- Runbook: upstream-recovery checklist.
```

- bullet 1, jitter: `grep -c random` on `v1.10.0:src/backoff.py` -> 0. **MISMATCH.**
  The section was written by `c62e5a513b84` on
  2024-05-25, after the removal on 2024-05-10.
- bullet 2, "warms to the configured target": `grep -c 'def start'` on
  `v1.10.0:src/pool.py` -> 0, and `grep -c warm_target` -> 0. **MISMATCH** — at that
  tag the pool does not warm at all, and the configured-target implementation
  `77b87636a12c` lands after the tag and first ships in v1.11.0.
- bullet 3, override file: `grep -c OVERRIDE_FILE` on `v1.10.0:src/config.py` -> 1. **MATCH.**
- bullet 4, runbook checklist: `grep -c 'Upstream recovery'` on `v1.10.0:docs/runbook.md` -> 1. **MATCH.**

The 1.11.0 section at HEAD:

```
## 1.11.0

- Single-writer-per-shard mode for the archival path.
- API surface returns the resolved shard in every response.
- Pool metrics exported on the health endpoint.
```

- bullet 1, single-writer mode: added by `1a581a950481`, tags containing it -> `pipeline-1.11-rc1 v1.11.0 `. **MATCH**, but see the decoy section.
- bullet 2, resolved shard: introduced by `0b24074a7835` on
  2024-03-23. Presence of `def resolved_shard` by tag:
    - `pipeline-1.11-rc1` -> 1
    - `v1.4.0` -> 0
    - `v1.5.0` -> 0
    - `v1.6.0` -> 0
    - `v1.7.0` -> 0
    - `v1.8.0` -> 1
    - `v1.9.0` -> 1
    - `v1.9.1` -> 1
    - `v1.10.0` -> 1
    - `v1.11.0` -> 1
  First release carrying it is `v1.8.0`, not 1.11.0. **MISATTRIBUTED.**
- bullet 3, pool metrics on the health endpoint: the only commit that mentions
  metrics is `a4c24c91e97a` ("api: prepare the pool metrics export"), whose diff is
  `3	0	src/api.py` and adds only a TODO comment:

```
  +
  +# TODO(metrics): export pool counters here once the platform sink accepts
  +# gauges. Nothing is emitted yet.
```

  `grep -ci 'gauge\|metric'` on `HEAD:src/api.py` -> 2, all of it comment text; there is no
  metrics export at any tag. **MISMATCH, supported only by a commit subject.**

## Layer 8 — the decoy: a "Revert" subject that is not a revert

`git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short 1a581a950481`:

```
1a581a9504818c7b15102e4d5ef5769d6c674e6c
Marcus Lindqvist
2024-06-09
Revert to a single writer per shard

Concurrent archival writers interleave and the compactor cannot tell which
segment is authoritative. Move the archival path back to one writer per shard
by adding an explicit owner claim.


 src/shard.py | 12 ++++++++++++
 1 file changed, 12 insertions(+)
```

- `git diff --numstat 1a581a950481^ 1a581a950481` -> `12	0	src/shard.py`
  — **insertions only, zero deletions**.
- it adds a new class, `class SingleWriterShard:`, to the shard module.
- nothing it could be undoing ever existed:
  `git log --all --format='%h %s' -i --grep='single writer'` ->
  `1a581a9 Revert to a single writer per shard;`
- tags containing it: `pipeline-1.11-rc1 v1.11.0 `
- so it is a **feature addition whose subject happens to begin with the word
  "Revert"** ("Revert to X" in the sense of "go back to X"). It must not be
  reported as part of any churn sequence.

## Quick index of the SHAs a claim may reference

| short | full | role |
|---|---|---|
| `9d8b9f69017f` | `9d8b9f69017f49053c253972c644ac0ee325ac71` | pre-warm landing 1, on `feature/prewarm`, warms max_size |
| `5b35d23fd6fd` | `5b35d23fd6fdc7f5c2136e355159b7131c4426a1` | merge that brought landing 1 to main |
| `f0a6be719e1d` | `f0a6be719e1d3118afbb94c6383ef7bd5d054018` | removal 1, a true revert |
| `245abbe660de` | `245abbe660deb54570912a17bef7c3c331776098` | POOL_WARM_TARGET knob |
| `5b995647c568` | `5b995647c56801bc777a66f589d340d99f4ca46b` | landing 2, same subject, lying cherry-pick trailer, warms min_size |
| `de96d2801b6f` | `de96d2801b6faafed12ba9aaa17f0b826d2f7f7b` | removal 2, subject says "simplify" |
| `77b87636a12c` | `77b87636a12c8dbd4b1d97a3d0324b7ca73f649a` | landing 3, configured warm target |
| `5f72d7d928c4` | `5f72d7d928c474fdfa5f503238f8503ceccdb076` | hotfix on the 1.9.1 branch |
| `3a3a3d0e6c5f` | `3a3a3d0e6c5f36ff5e5239375b2bb0893c6db195` | same hotfix forward-ported to main |
| `7cb3e9ec9742` | `7cb3e9ec9742e55ee3bee59e28e06e5362861680` | src/retry.py -> src/backoff.py |
| `751bf0341da0` | `751bf0341da0f42a5bd67a09bd20745feb2c428d` | jitter landed |
| `121e3672ca26` | `121e3672ca266afb9c42853595b6f708867e88e9` | jitter removed, never restored |
| `c5e230551893` | `c5e2305518937611b429a8982fbfd4d2da9259f2` | "Revert of the revert" that restores nothing |
| `0b24074a7835` | `0b24074a783546303cb0b3511401710afa7694f1` | resolved_shard(), miscredited to 1.11.0 |
| `a4c24c91e97a` | `a4c24c91e97a5288943816b7026204df708ccf97` | metrics subject with no metrics |
| `1a581a950481` | `1a581a9504818c7b15102e4d5ef5769d6c674e6c` | decoy: "Revert to a single writer per shard" |
| `aa86ca39961c` | `aa86ca39961cd50b84023a9002fc38a6ac1054ba` | HEAD / pinned branch tip |
