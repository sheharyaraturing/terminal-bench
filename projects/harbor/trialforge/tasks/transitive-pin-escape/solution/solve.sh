#!/bin/bash
# ORACLE SOLUTION, the acceptance gate.
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
# Every SHA and version below came from a fresh clone of
# fixtures/metrics-etl.bundle; see environment/fixtures/GROUND_TRUTH.md.

set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Nadia, the pandas pin is not what broke the export. It is a real change and it
did loosen a pin, but pandas is byte-for-byte the same version either side of
the boundary. What moved is botocore, which nothing in this repository names,
and the only reason it could move is that we deleted our lockfile one release
before the failure showed up.

SCOPE

main is 52 commits, strictly linear, no merge commits, one author, 2024-01-08 to
2024-07-30, 12 tracked files. Eight release tags: v2.4.0, v2.5.0, v2.6.0,
v2.7.0, v2.8.0, v2.9.0, v2.10.0, v2.11.0.

1. THE FAILURE BOUNDARY

The incident record added on 2024-07-06 puts the first failing release at 2.10.0
and says the same input replayed on the previous release completes. Semantically
the previous release is v2.9.0, not, as the lexical tag order suggests, v2.11.0
or v2.4.0. So:

  last release that ran clean : v2.9.0   (tag commit aeba6ea, 2024-06-04)
  first release that fails    : v2.10.0  (tag commit da8975c, 2024-06-28)

Recorded symptom, from the incident note:

    TypeError: complete_multipart_upload() got an unexpected keyword argument
    'ChecksumCRC32'

raised inside the AWS client call in ParquetSink.complete() in the S3 sink. The
sink has not been touched since 2.8.0.

And critically: `git diff v2.9.0 v2.10.0 -- requirements.txt constraints.txt`
is EMPTY. Neither file we maintain by hand changed between the two releases, so
the cause is not in the declared dependencies at all.

2. THE PIN THAT WAS LOOSENED, AND WHY IT IS NOT THE CAUSE

  aa730ca  2024-05-19  deps: loosen the pandas pin
           (full SHA aa730ca9d7644a2883615b0508faf5517a8605f0)

One insertion, one deletion, one file:

    -pandas==2.1.4
    +pandas>=2.1,<3

The recorded reason is in the commit body: the copy-on-write work needed pandas
2.2 and the project was pinned to 2.1.4, so the pin had to come off before the
rollup change could land; a range was chosen rather than a straight bump so we
would not be chasing patch releases every fortnight.

That work is traceable and it exonerates the pin twice over. The rollup path was
switched to copy-on-write at 03a58ab four days after the pin came off, and that
commit first ships in v2.9.0. So the relaxation and the change it was made for
both went out in v2.9.0, which is the LAST RELEASE THAT RAN CLEAN. pandas had
already proved itself in a working release before the export ever failed.

It first shipped in **v2.9.0**. Be careful here, `git tag --contains aa730ca`
prints v2.10.0, v2.11.0, v2.9.0, in that order, because git sorts tag names
lexically and "2.1" sorts before "2.9". Taking the first line gives v2.10.0,
which is wrong by a release. Sort by version, not by string.

Now the part that settles it. The release job records what each build actually
resolved to, and pandas reads:

    v2.4.0 ... v2.8.0   pandas==2.1.4
    v2.9.0            pandas==2.2.2
    v2.10.0           pandas==2.2.2
    v2.11.0           pandas==2.2.2

pandas is IDENTICAL at v2.9.0 and v2.10.0. The loosened pin changed what shipped
between v2.8.0 and v2.9.0, and v2.9.0 built and ran clean. So the loosening
does not explain a failure that starts at v2.10.0. Rule it out.

3. WHAT ACTUALLY MOVED

Comparing the recorded dependency sets at the two tags: 19 packages at each,
none added, none removed, and exactly FOUR version changes.

    botocore            1.34.88   -> 1.35.14
    certifi             2024.2.2  -> 2024.7.4
    charset-normalizer  3.3.2     -> 3.3.4
    idna                3.6       -> 3.7

Three of those four are not on the failing path. The resolution parents recorded
alongside each package say so: certifi and charset-normalizer arrive via
requests, and idna via requests and the async URL library behind aiohttp. None
of them is involved in an S3 multipart upload.

botocore is. The sink imports the S3 filesystem package and calls
complete_multipart_upload on the client that package owns, and that client is
botocore's. A 1.34 to 1.35 move in botocore is exactly the kind of change that
starts sending a checksum keyword the older client never saw. That is the cause.

For contrast, the same comparison one release earlier (v2.8.0 to v2.9.0) shows
eight movers including pandas and pyarrow and did not break anything, and one
release later (v2.10.0 to v2.11.0) shows six, botocore among them at 1.35.29, still on the 1.35 series, which is why 2.11.0 is still failing.

4. HOW BOTOCORE GETS IN, AND WHY NOTHING HELD IT

botocore is a **transitive** dependency. We never ask for it. It arrives through
our direct requirement on the S3 filesystem package, by way of that package's
async AWS client wrapper, the recorded set annotates it as coming via
aiobotocore and via s3fs.

And it appears in NEITHER of the two files we maintain. Not in the direct
requirements, not in the constraints, at any commit in all 52. I checked every
revision of both files: zero occurrences. The constraints file holds four
entries, numpy, pytz, six, urllib3, and the direct requirements hold five:
click, pandas, pyarrow, requests, s3fs. Nothing there can constrain botocore.

The point that matters for the post-mortem: everything we DO pin held. s3fs sat
at 2024.5.0 on both sides of the boundary and aiobotocore at 2.12.3 on both
sides, yet botocore moved underneath them from 1.34.88 to 1.35.14. So this is
not a pin that failed, it is a package two hops down that no pin of ours ever
covered. The constraints file could not have caught it: it names numpy, pytz,
six and urllib3, none of which is on that chain.

botocore across every release:

    v2.4.0  1.34.34    v2.8.0  1.34.51
    v2.5.0  1.34.39    v2.9.0  1.34.88
    v2.6.0  1.34.44    v2.10.0 1.35.14
    v2.7.0  1.34.48    v2.11.0 1.35.29

5. THE LOCKFILE, WE HAD PROTECTION AND WE DELETED IT

  2e8bfe9  2024-04-21  build: install from a fully resolved lockfile
           (full SHA 2e8bfe913ce323e7b14aadbf2cd099d11c69a5fb)
  b512dac  2024-05-07  build: stop installing from the lockfile
           (full SHA b512dac553912e83068484b7ab568931ef0e53a6)

2e8bfe9 committed a fully resolved lockfile with 19 hard pins, botocore==1.34.51
among them, and pointed the install target at it. b512dac deleted it sixteen
days later, the recorded reason is that the file went stale and the refresh job
kept losing a race with the security-update bot, and pointed the install target
back at requirements plus constraints.

**Exactly one tagged release ever carried that file: v2.8.0.** I checked each
tag directly rather than trusting containment: the file exists at v2.8.0 and is
absent at v2.4.0 through v2.7.0 and at v2.9.0, v2.10.0 and v2.11.0.

That distinction matters, because `git tag --contains 2e8bfe9` returns four tags, v2.8.0, v2.9.0, v2.10.0, v2.11.0, since the commit that added the file is an
ancestor of all four. Containment of the commit is not presence of the file.
Only the tag that falls between the add and the delete has it. So the answer to
"which releases were protected" is one, not four.

Note the timing. Protection lapsed at v2.9.0, not at v2.10.0. v2.9.0 shipped
with no lockfile and still resolved botocore to 1.34.88, so it ran clean by luck.
The escape opened one release before the failure became visible, which is why
nobody connected the lockfile removal to the outage.

The changelog does not help here: the 2.8.0 section advertises installing from a
fully resolved lockfile, and no later section mentions that it was removed.

6. NOT A DEPENDENCY CHANGE, STOP RE-READING IT

  d85a5a8  2024-05-15  deps: tidy up constraints.txt

Nine insertions, four deletions in the constraints file, four days before the
pandas loosening, with a body about holding urllib3 back. It changes no version.
It sorts the four existing constraints alphabetically, adds a comment block, and
pads the == operators with spaces. Reduced to name==version with whitespace
stripped, before and after are identical:

    numpy==1.26.4  pytz==2024.1  six==1.16.0  urllib3==1.26.18

So in that window there is exactly ONE commit that changes a declared version, aa730ca, and it is the one we just ruled out.

7. THE RELEASE NOTES ARE MISLEADING BY OMISSION

The 2.8.0 entry says builds install from a fully resolved lockfile, "so two
builds of the same commit get the same dependency versions". That was true when
it was written. Installing from the lockfile stopped on 2024-05-07 at b512dac,
because the file had gone stale and its refresh job kept losing a race with the
security bot, so CI was failing on hash mismatches rather than on real problems.

No entry anywhere records that. The notes still advertise reproducible builds
and never withdraw the claim. Anyone reading them, which is to say anyone
outside the build team, would believe the guarantee still held right through the
releases where it did not.

8. THE WRITE-UP IS WRONG ON ONE POINT

The incident note says our code has not been touched since 2.8.0. That is not
true: src/sink_s3.py was changed on 2024-07-10 by 527ec56, "sink: turn the
completion failure into a legible error".

It does not rescue the note's conclusion, and it is not the cause. The commit
adds six lines and removes none: a complete_guarded() wrapper that calls
complete(), catches the TypeError and re-raises it as a RuntimeError with a
readable message. No behaviour changes, and nothing in the tree ever calls the
wrapper. It is also carried by v2.11.0 alone, so it was not present in 2.10.0 or
any earlier release, which is where the failures are.

So the note reached the right conclusion from a premise that does not hold. Fix
the premise, keep the conclusion.

9. THE FIX

Pin botocore explicitly. Add

    botocore==1.34.88

to the constraints file, so the pin exists even though nothing requires botocore
by name, and roll a 2.11.1 with it. That gets the nightly export back tonight.

Then restore the lockfile properly and install from it, and give the refresh job
an owner, a constraints entry only holds the one package we happened to get
burned by, and of the 14 transitive packages in the recorded set 10 have nothing
pinning them at all, botocore plus nine others. Re-tightening the pandas pin would achieve nothing:
pandas was never the problem.
EOF
