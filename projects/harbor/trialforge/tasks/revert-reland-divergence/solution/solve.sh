#!/bin/bash
# ORACLE SOLUTION — the acceptance gate.
#
# Harbor runs this instead of an agent when invoked with `-a oracle`. Its output
# must satisfy EVERY claim in tests/reward.toml, because "oracle scores 1.0" is
# what proves the task is solvable and the verifier accepts a correct answer.
#
# WRITE TO BOTH PATHS. /logs/agent is what a shared-mode run reads;
# /logs/artifacts is what a SEPARATE verifier reads and the only one recorded
# into the trial. An oracle that only echoes to stdout scores 0.0 under
# environment_mode = "separate".
#
# Every SHA, blob hash, diff stat and VERSION string below came from a fresh
# clone of fixtures/pipeline-svc.bundle; see environment/fixtures/GROUND_TRUTH.md.

set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Dana — sign-off memo for 1.11. Do not ship the draft notes as written.

I worked from the commit graph and from the trees the tags actually point at. I
did not use commit subjects, diffstats, cherry-pick trailers or
`git tag --contains` as evidence, because in this repository each of those is
wrong about something. Where I rely on a fact, the object it came from is named.

1. THE PRE-WARM CHURNED THREE TIMES, NOT ONCE

The change is the connection-pool pre-warming in src/pool.py: a _prewarm(count)
helper that opens connections up to `count`, called from a start() method. Its
complete sequence is three landings and two removals:

  landing 1  9d8b9f69017f49053c253972c644ac0ee325ac71  (9d8b9f6)  2024-03-11
             "Pre-warm the connection pool on worker start"  (Marcus Lindqvist)
             on branch feature/prewarm; warms self.max_size
  merge      5b35d23fd6fdc7f5c2136e355159b7131c4426a1  (5b35d23)  2024-03-17
             "Merge branch 'feature/prewarm' into main"
  removal 1  f0a6be719e1d3118afbb94c6383ef7bd5d054018  (f0a6be7)  2024-03-26
             Revert "Pre-warm the connection pool on worker start"
  landing 2  5b995647c56801bc777a66f589d340d99f4ca46b  (5b99564)  2024-04-07
             "Pre-warm the connection pool on worker start"  (Priya Raghunathan)
             warms self.min_size
  removal 2  de96d2801b6faafed12ba9aaa17f0b826d2f7f7b  (de96d28)  2024-05-22
             "pool: simplify worker start-up"  (Aiko Tanabe)
  landing 3  77b87636a12c8dbd4b1d97a3d0324b7ca73f649a  (77b8763)  2024-05-31
             "pool: warm the pool to the configured target"  (Marcus Lindqvist)
             warms self.warm_target()

Anyone who stops at "landed, reverted, re-landed" has three quarters of the
story and the wrong conclusion about what is in 1.11.

HOW THE FIRST LANDING ENTERED, AND WHY ONE LOG IS NOT ENOUGH

9d8b9f6 was never committed on main. It sits on the side branch
feature/prewarm and reached main through 5b35d23, the only merge commit in the
history (`git rev-list --count --merges HEAD` = 1). That matters because
neither obvious view of the module's history is complete:

  - `git log -- src/pool.py` lists 9d8b9f6 but NOT the merge 5b35d23: history
    simplification drops a merge that is TREESAME to one of its parents.
  - `git log --first-parent -- src/pool.py` lists 5b35d23 but NOT 9d8b9f6,
    because the landing is on the second parent.

Reading only the first gives a landing with no visible route to main; reading
only the second gives a merge with no visible author or rationale. Both are
needed. (Unrelated but worth knowing when counting commits: 9a4882f
"chore: retrigger the release pipeline" is an empty commit with no diff at all.)

RECORDED REASON FOR THE FIRST REMOVAL

Quoted from f0a6be7's body: "This reverts the pre-warm change. On the deploy
that carried it every worker opened its full ceiling of connections
simultaneously and we tripped the upstream connection limit inside forty
seconds. Reverting to unblock the release; we will bring it back once the warm
target is sane."

f0a6be7 really is a back-out, and I checked that by content rather than by its
subject: src/pool.py at f0a6be7 is the same blob as src/pool.py at 9d8b9f6's
parent — a2d81b3 (a2d81b37f2dda5479425fb553bfb86fbdec0367c) in both.

2. THE SECOND LANDING'S COMMIT MESSAGE IS FALSE

5b99564's body reads:

    Rolling this forward again for the 1.9 cycle now that there is a warm-target
    knob to hang it off.

    (cherry picked from commit 9d8b9f69017f49053c253972c644ac0ee325ac71)

The trailer names landing 1. It is not landing 1. Scoped to src/pool.py the diff
between them is one insertion and one deletion:

    @@ -43,4 +43,4 @@ class ConnectionPool:
                     self._idle.append(self.factory())

         def start(self):
    -        self._prewarm(self.max_size)
    +        self._prewarm(self.min_size)

Pool blobs: 73f71e9 at landing 1, c6431cd at landing 2.

NEITHER CHEAP COMPARISON SEPARATES THEM

  - The subjects are byte-identical: both are "Pre-warm the connection pool on
    worker start", so a subject grep returns two commits, authored by two
    different people (Marcus Lindqvist, then Priya Raghunathan — and 5b99564's
    committer is Marcus, not its author).
  - Each commit read on its own is 10 insertions, 0 deletions, touching only
    src/pool.py. By their own diffstats they are indistinguishable.

The divergence exists only in a diff of the two revisions against each other.
A trailer plus matching diffstats is exactly the evidence that would convince a
release engineer they are identical, and it is wrong.

WHY THAT ONE LINE IS THE WHOLE POINT

ConnectionPool.__init__ defaults are min_size=2 and max_size=32. Landing 1
warmed self.max_size, so every worker opened its full allowance of 32
connections at start-up — precisely the failure f0a6be7 records. Landing 2 warms
self.min_size, which is 2. Supporting change: 245abbe660deb54570912a17bef7c3c331776098
(245abbe, 2024-04-04, "config: add a pool warm target knob") added
POOL_WARM_TARGET = "min" to src/config.py immediately before landing 2, which is
the knob the message refers to.

3. THE SECOND REMOVAL NEVER SAYS "REVERT"

  de96d2801b6faafed12ba9aaa17f0b826d2f7f7b  (de96d28)  2024-05-22
  "pool: simplify worker start-up"  —  Aiko Tanabe

Its diff is 0 insertions and 10 deletions in src/pool.py: it deletes both
_prewarm() and start(), and leaves the module on blob a2d81b3 — the same state
the first removal produced. Body: "Take the start-up path back to the plain
constructor and let the pool fill on demand."  (Recorded reason, quoted in full:
take the start-up path back to the plain constructor / let the pool fill on
demand.)

Nothing in the subject or body says revert, back out, or remove. Every
subject-based search for removals misses it, which is why the pre-warm looks
like it survived from 1.9.0 onward when it did not.

4. THE THIRD LANDING IS A THIRD DESIGN

77b8763 does not restore either earlier version. It adds a new method:

    def warm_target(self):
        """Resolve the configured warm target to a connection count."""
        from src.config import POOL_WARM_TARGET

        if POOL_WARM_TARGET == "max":
            return self.max_size
        if POOL_WARM_TARGET == "off":
            return 0
        return self.min_size

    def start(self):
        self._prewarm(self.warm_target())

That is a 20-insertion change, not the 10-line change that landed twice before.
The argument handed to _prewarm at each landing: self.max_size, then
self.min_size, then self.warm_target(). No two of the three are the same change,
and only the survivor is configuration-driven — the ceiling case is still
reachable, but only by setting POOL_WARM_TARGET = "max".

5. WHAT EACH RELEASE ACTUALLY SHIPPED

Tag inventory before any first-shipped claim. Ten tags exist. For each: type,
pointed-at commit, VERSION in the tagged tree, release?:

  v1.4.0           lightweight  → 81c270d…  VERSION="1.4.0"   release
  v1.5.0           lightweight  → 00e33ae…  VERSION="1.5.0"   release
  v1.6.0           lightweight  → 26dd765…  VERSION="1.6.0"   release
  v1.7.0           lightweight  → 29f455c…  VERSION="1.7.0"   release
  v1.8.0           lightweight  → fe6131e…  VERSION="1.8.0"   release
  v1.9.0           lightweight  → 4f91f5d…  VERSION="1.9.0"   release
  v1.9.1           lightweight  → 8cdab8e…  VERSION="1.9.1"   release (hotfix line)
  v1.10.0          annotated    → c62e5a5…  VERSION="1.9.0"   release (name lies)
  v1.11.0          annotated    → 6d92d0d…  VERSION="1.11.0"  release
  pipeline-1.11-rc1 lightweight → 842f2d3…  VERSION="1.10.0"  NOT a release (rc)

Read from src/pool.py in each tagged tree, not from the notes:

  v1.4.0   no pre-warm
  v1.5.0   no pre-warm
  v1.6.0   no pre-warm
  v1.7.0   no pre-warm
  v1.8.0   no pre-warm
  v1.9.0   pre-warm, warms self.min_size
  v1.9.1   no pre-warm
  v1.10.0  no pre-warm
  v1.11.0  pre-warm, warms self.warm_target()

Jittered backoff presence from the tagged trees (src/backoff.py or pre-rename
src/retry.py as applicable): absent at v1.4.0, v1.5.0, v1.6.0, v1.7.0, v1.8.0,
v1.9.0, v1.9.1, v1.10.0 and v1.11.0 — every release. It churned between commits
and shipped in no release at all.

So the pre-warm feature shipped in 1.9.0, silently regressed out for 1.9.1 and 1.10.0,
and returned in 1.11.0 as a different implementation. Two first-shipped facts
must not be collapsed: first-shipped of any form is v1.9.0 (the min_size
implementation); first-shipped of the surviving configured-target form is
v1.11.0. "Pre-warming shipped in 1.9.0" is true only of a version that no longer
exists, and "and has been there since" is false.

THE TAG SURFACE IS UNRELIABLE IN THREE SEPARATE WAYS

  a. Commit containment is not release presence. `git tag --contains 9d8b9f6`
     lists pipeline-1.11-rc1, v1.8.0, v1.9.0, v1.9.1, v1.10.0 and v1.11.0 — but
     v1.8.0, v1.9.1 and v1.10.0 have no pre-warm at all. The landing commit is
     reachable from those tags and so is a removal, so containment answers a
     different question than the one being asked.
  b. The earliest tag containing the surviving implementation 77b8763, by
     version sort, is pipeline-1.11-rc1 — a release candidate, not a release.
     The first release is v1.11.0.
  c. v1.10.0 is an annotated tag, and it was cut before the version bump
     03a1d46 ("release: bump VERSION to 1.10.0"). src/config.py at v1.10.0 still
     says VERSION = "1.9.0". Anything that identifies a release by the VERSION
     constant will mis-file everything at that tag.

1.9.1 IS NOT A LATER STATE OF 1.9.0

`git merge-base --is-ancestor v1.9.0 v1.9.1` is false. The hotfix was branched
from f0a6be7 — the first removal — so v1.9.1 never contained the pre-warm even
though its version number is higher than v1.9.0's. What 1.9.1 is missing
relative to 1.9.0 includes landing 2 itself and the 1.8.0 release commit. The
hotfix also exists twice as two distinct commits with the same subject
"shard: guard against an empty routing table": 5f72d7d on the unmerged
hotfix/1.9.1 branch, and 3a3a3d0 forward-ported onto main with a faithful
cherry-pick trailer naming 5f72d7d.

6. THE BACKOFF MODULE WAS RENAMED, THEN CHURNED

7cb3e9ec9742e55ee3bee59e28e06e5362861680 (7cb3e9e, 2024-05-01, "retry: move the
backoff policy to src/backoff.py") is a pure rename of src/retry.py to
src/backoff.py — `git show --stat` reports it as
`src/{retry.py => backoff.py} | 0`. Plain-vs-follow counts: a plain
`git log --oneline -- src/backoff.py` is **4 commits** and stops at the rename;
`git log --oneline --follow -- src/backoff.py` is **6 commits** and adds the
pre-rename history, including "retry: cap the computed delay at max_delay" and
the initial import. Any audit of the retry behaviour that does not follow the
rename is reading a truncated file history.

  jitter landed   751bf0341da0f42a5bd67a09bd20745feb2c428d  (751bf03)  2024-05-07
  jitter removed  121e3672ca266afb9c42853595b6f708867e88e9  (121e367)  2024-05-10

Recorded reason, from 121e367: "The replay harness is seeded and asserts exact
delays, so a non-deterministic delay_for() makes the whole suite flap. Reverting
for now; needs an injectable random source before it can go back in."

7. A SUBJECT THAT CLAIMS A RESTORATION THAT NEVER HAPPENED

  c5e2305518937611b429a8982fbfd4d2da9259f2  (c5e2305)  2024-05-13
  Revert "Revert \"Add jittered exponential backoff to the retry loop\""
  body: "Bringing the jitter change back for the 1.10 cycle now that the harness
  can inject its own clock."

The subject and body both say the jitter is back. The diff restores nothing —
it adds two comment lines to src/backoff.py and no code:

    +        # Jitter needs an injectable clock before it can come back; the replay
    +        # harness asserts exact delays and a seeded source is not wired up yet.

Evidence from the trees rather than the subjects: no occurrence of "random" in
src/backoff.py at v1.10.0, at v1.11.0, or at HEAD. The removal 121e367 had
restored the pre-jitter blob bf6f257 exactly, and the only change to the module
since is that comment. The jitter has never shipped in any release.

8. DRAFT NOTES, ITEM BY ITEM

1.10.0 — four bullets, two wrong and two right:

  - "Jittered exponential backoff in the retry loop, which removes the
    thundering-herd spike…" — MISMATCH. No randomness at v1.10.0. The section
    was written by c62e5a5 ("docs: changelog for 1.10.0") on 2024-05-25, fifteen
    days after the removal on 2024-05-10, so it was false the day it was written,
    and c5e2305's misleading subject is the likely reason the author believed it.
  - "The connection pool warms to the configured target on worker start." —
    MISMATCH. At v1.10.0 src/pool.py has no start() and no warm_target() at all,
    because de96d28 removed the pre-warm before the tag was cut. The
    configured-target implementation 77b8763 lands after the tag and first ships
    in v1.11.0. This bullet describes 1.11.0's behaviour, filed under 1.10.0.
  - "Config loader accepts a per-environment override file." — MATCH.
    OVERRIDE_FILE is in src/config.py at v1.10.0.
  - "Runbook: upstream-recovery checklist." — MATCH. Present in
    docs/runbook.md at v1.10.0.

The notes also omit entirely the silent pre-warm regression: present at v1.9.0,
absent at v1.9.1 and v1.10.0, returned only later in a different form. That
omission is as material as the false bullets.

1.11.0 — three bullets:

  - "Single-writer-per-shard mode for the archival path." — MATCH as code, but
    mislabelled in history: see section 9.
  - "API surface returns the resolved shard in every response." — MISATTRIBUTED.
    The code is real, but resolved_shard() was added by
    0b24074a783546303cb0b3511401710afa7694f1 (0b24074, 2024-03-23). Presence in
    the tagged trees: absent at v1.4.0–v1.7.0, present from v1.8.0 onward. It
    first shipped three releases before the note credits it. Crediting 1.11.0
    is wrong.
  - "Pool metrics exported on the health endpoint." — MISMATCH, and supported
    only by a commit subject. There is no metrics export at any tag. The only
    commit that mentions metrics is
    a4c24c91e97a5288943816b7026204df708ccf97 (a4c24c9, "api: prepare the pool
    metrics export"), whose entire diff is a three-line TODO comment saying
    nothing is emitted yet. Nothing in src/api.py emits a gauge or a counter.

9. A "REVERT" SUBJECT THAT IS A FEATURE ADDITION

  1a581a9504818c7b15102e4d5ef5769d6c674e6c  (1a581a9)  2024-06-09
  "Revert to a single writer per shard"  —  Marcus Lindqvist

Not a back-out. The diff is 12 insertions and 0 deletions in src/shard.py,
adding a new class SingleWriterShard with an owner-claim method. Nothing is
removed.

Negative result: nothing it could have been undoing ever existed. Searching all
refs for "single writer" returns only 1a581a9 itself, and the shard module's
earlier commits (997c25c, 1828cd8, 9994ce4, 3a3a3d0) add lag reporting,
incremental rebalancing, stable ordering and an empty-table guard on top of the
initial routing table — never a multi-writer archival path. The
subject means "revert to X" in the English sense of returning to a state, not a
git revert of a commit.

It ships in v1.11.0 (and in pipeline-1.11-rc1), and it does not belong in the
churn sequences above. The churn in this repository is exactly two changes: the
pre-warm, which left twice and came back three times in three forms, and the
jitter, which left once and never came back.

10. SIGN-OFF ASSESSMENT

Not safe to approve. Corrections required before I sign:

  - Delete the jitter bullet from 1.10.0. It has never shipped, in any release,
    and c5e2305's subject is not evidence that it did.
  - Delete or re-file the "warms to the configured target" bullet from 1.10.0.
    1.10.0 shipped with no pre-warming at all; the configured-target behaviour
    belongs to 1.11.0.
  - Record the regression the notes never mention: pre-warming shipped in 1.9.0,
    was absent from 1.9.1 and 1.10.0, and returns in 1.11.0 in a different form.
  - Re-credit the resolved-shard bullet from 1.11.0 to 1.8.0.
  - Delete the pool-metrics bullet from 1.11.0, or implement it.
  - Keep the single-writer bullet, and note in the release record that 1a581a9
    is a feature addition, not a back-out, so future audits do not read it as one.
EOF
