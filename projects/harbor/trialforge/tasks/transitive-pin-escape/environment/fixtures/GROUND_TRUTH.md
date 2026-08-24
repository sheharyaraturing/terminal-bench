# GROUND_TRUTH.md — transitive-pin-escape

Everything below is the **output of commands run against a fresh clone of
`metrics-etl.bundle`**, not against the builder's working tree. `bash
build_fixture.sh` rebuilds the bundle and regenerates this file, so the SHAs
below are the SHAs an agent will see.

Read-back procedure:

```
git clone metrics-etl.bundle readback
cd readback && git checkout -B main 6d120f7400623a25d7d5e08ff0b2dff101bf130b
```

## Shape of the repository

- pinned branch tip (the SHA `environment/Dockerfile` checks out as `main`):
  `6d120f7400623a25d7d5e08ff0b2dff101bf130b`
- `git cat-file -t 6d120f7400623a25d7d5e08ff0b2dff101bf130b` in the clone -> `commit`
- `git rev-list --count HEAD` -> **52** commits, single linear branch
  (`git rev-list --count --merges HEAD` -> 0 merge commits)
- tracked files at HEAD (12):
  - `CHANGELOG.md`
  - `Makefile`
  - `README.md`
  - `build/README.md`
  - `build/sbom.txt`
  - `constraints.txt`
  - `docs/incidents/2024-07-nightly-export.md`
  - `requirements.txt`
  - `src/cli.py`
  - `src/frame.py`
  - `src/sink_s3.py`
  - `tests/test_frame.py`
- author on every commit: `Tomas Berglund <tomas.berglund@example.invalid> `
- first commit 2024-01-08, last commit 2024-07-30

### Tags carried by the bundle

`git tag` (git's own default ordering, which is lexical):

```
v2.10.0
v2.11.0
v2.4.0
v2.5.0
v2.6.0
v2.7.0
v2.8.0
v2.9.0
```

Lexical order puts `v2.10.0` and `v2.11.0` **before** `v2.4.0`. Semantic order
is v2.4.0 < v2.5.0 < v2.6.0 < v2.7.0 < v2.8.0 < v2.9.0 < v2.10.0 < v2.11.0.
`sort -V` agrees with semantic order:

```
v2.4.0
v2.5.0
v2.6.0
v2.7.0
v2.8.0
v2.9.0
v2.10.0
v2.11.0
```

Tag -> commit:

  - `v2.4.0` -> `cf7d282d6dda`  2024-02-01
  - `v2.5.0` -> `abff643a973e`  2024-02-25
  - `v2.6.0` -> `25c660c27f8c`  2024-03-16
  - `v2.7.0` -> `7b3f5ef5b99e`  2024-04-05
  - `v2.8.0` -> `ba62cffa661c`  2024-05-03
  - `v2.9.0` -> `aeba6ea519d0`  2024-06-04
  - `v2.10.0` -> `da8975c2169d`  2024-06-28
  - `v2.11.0` -> `621f89a5bd89`  2024-07-22

## What the two dependency input files ever contain

`git log --format='%h %ad %s' --date=short -- requirements.txt constraints.txt requirements.lock`:

```
621f89a 2024-07-22 release: 2.11.0
aeba6ea 2024-06-04 release: 2.9.0
aa730ca 2024-05-19 deps: loosen the pandas pin
d85a5a8 2024-05-15 deps: tidy up constraints.txt
b512dac 2024-05-07 build: stop installing from the lockfile
2e8bfe9 2024-04-21 build: install from a fully resolved lockfile
7b3f5ef 2024-04-05 release: 2.7.0
25c660c 2024-03-16 release: 2.6.0
dac806a 2024-01-08 Initial import of metrics-etl
```

`requirements.txt` at HEAD:

```
# Direct requirements for metrics-etl.
# Installed with:  pip install -r requirements.txt -c constraints.txt
click==8.1.7
pandas>=2.1,<3
pyarrow==17.0.0
requests==2.31.0
s3fs==2024.6.1
```

`constraints.txt` at HEAD:

```
# Transitive constraints. Sorted; keep it that way so the audit diff is
# readable. Applied with -c on every install.
#
# urllib3 is held on the 1.26 series because the vendored TLS shim in our
# base image has not been rebuilt against 2.x yet.
numpy == 1.26.4
pytz == 2024.1
six == 1.16.0
urllib3 == 1.26.18
```

Neither file ever names botocore, at any commit:

```
git log --all --format='%h' -- requirements.txt constraints.txt \
  | while read c; do git show $c:requirements.txt $c:constraints.txt; done | grep -c botocore
-> 0
```

Direct requirements at HEAD: **5**.
Constraint entries at HEAD: **4**.

## Layer 1 — the direct pin that was loosened

| field | value |
|---|---|
| full SHA | `aa730ca9d7644a2883615b0508faf5517a8605f0` |
| short | `aa730ca9d764` |
| date | 2024-05-19 |
| subject | deps: loosen the pandas pin |

`git show --format= -U0 aa730ca9d764 -- requirements.txt`:

```
diff --git a/requirements.txt b/requirements.txt
index 4273afc..4b7ba34 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -4 +4 @@ click==8.1.7
-pandas==2.1.4
+pandas>=2.1,<3
```

`git show --numstat --format= aa730ca9d7644a2883615b0508faf5517a8605f0`:

```
1	1	requirements.txt
```

Commit body:

```
The copy-on-write work needs pandas 2.2 and we are pinned to 2.1.4, so the
pin has to come off before the rollup change can land. Range rather than a
straight bump so we are not chasing patch releases every fortnight.
```

### Which release the loosening first shipped in — the tag-ordering trap

`git tag --contains aa730ca9d764` prints, in git's own order:

```
v2.10.0
v2.11.0
v2.9.0
```

That is **lexical**. `sort -V` on the same set:

```
v2.9.0
v2.10.0
v2.11.0
```

So the first line of the naive command is `v2.10.0` and the correct
answer is **`v2.9.0`**.

## Layer 2a — the loosened pandas pin is not the cause

pandas as RECORDED IN THE AUDIT SNAPSHOT at each release
(`git show <tag>:build/sbom.txt | grep -A1 '^pandas=='`):

  - `v2.4.0` -> `pandas==2.1.4`
  - `v2.5.0` -> `pandas==2.1.4`
  - `v2.6.0` -> `pandas==2.1.4`
  - `v2.7.0` -> `pandas==2.1.4`
  - `v2.8.0` -> `pandas==2.1.4`
  - `v2.9.0` -> `pandas==2.2.2`
  - `v2.10.0` -> `pandas==2.2.2`
  - `v2.11.0` -> `pandas==2.2.2`

pandas is **identical at v2.9.0 and v2.10.0**, so the loosened pin changed
nothing across the failure boundary. It did change what shipped between v2.8.0
and v2.9.0 — and v2.9.0 built clean.

## Layer 2b — what actually moved across the failure boundary

The incident record (`docs/incidents/2024-07-nightly-export.md`, added by
3056ccb34f86) puts the
first failing release at 2.10.0 and the last good one at its predecessor.

`python3 cmp.py v2.9.0 v2.10.0` — parses `build/sbom.txt` out of both tags
with independent code and diffs the pins:

```
packages recorded at v2.9.0: 19
packages recorded at v2.10.0: 19
added: []  removed: []
version changes (4):
  botocore: 1.34.88 -> 1.35.14
  certifi: 2024.2.2 -> 2024.7.4
  charset-normalizer: 3.3.2 -> 3.3.4
  idna: 3.6 -> 3.7
```

For contrast, the same comparison one release earlier:

```
packages recorded at v2.8.0: 19
packages recorded at v2.9.0: 19
added: []  removed: []
version changes (8):
  aiobotocore: 2.12.1 -> 2.12.3
  aiohttp: 3.9.3 -> 3.9.5
  botocore: 1.34.51 -> 1.34.88
  fsspec: 2024.3.1 -> 2024.5.0
  pandas: 2.1.4 -> 2.2.2
  pyarrow: 15.0.2 -> 16.1.0
  python-dateutil: 2.8.2 -> 2.9.0
  s3fs: 2024.3.1 -> 2024.5.0
```

and one release later:

```
packages recorded at v2.10.0: 19
packages recorded at v2.11.0: 19
added: []  removed: []
version changes (6):
  aiobotocore: 2.12.3 -> 2.15.1
  aiohttp: 3.9.5 -> 3.10.5
  botocore: 1.35.14 -> 1.35.29
  fsspec: 2024.5.0 -> 2024.6.1
  pyarrow: 16.1.0 -> 17.0.0
  s3fs: 2024.5.0 -> 2024.6.1
```

### Why botocore and not the other three

The `# via` annotations in the snapshot give the resolution parents. At v2.10.0:

```
botocore==1.35.14
    # via
    #   aiobotocore
    #   s3fs
certifi==2024.7.4
    # via requests
charset-normalizer==3.3.4
    # via requests
idna==3.7
    # via
    #   requests
    #   yarl
```

`src/sink_s3.py` imports `s3fs` and calls `complete_multipart_upload` on the
client s3fs owns; certifi, charset-normalizer and idna arrive via `requests`
and `aiohttp`/`yarl` and are not on that path. botocore is the only one of the
four that is.

botocore across every release:

  - `v2.4.0` -> `botocore==1.34.34`
  - `v2.5.0` -> `botocore==1.34.39`
  - `v2.6.0` -> `botocore==1.34.44`
  - `v2.7.0` -> `botocore==1.34.48`
  - `v2.8.0` -> `botocore==1.34.51`
  - `v2.9.0` -> `botocore==1.34.88`
  - `v2.10.0` -> `botocore==1.35.14`
  - `v2.11.0` -> `botocore==1.35.29`

## Layer 2c — the lockfile that existed for exactly one release

| event | full SHA | short | date | subject |
|---|---|---|---|---|
| added | `2e8bfe913ce323e7b14aadbf2cd099d11c69a5fb` | `2e8bfe913ce3` | 2024-04-21 | build: install from a fully resolved lockfile |
| deleted | `b512dac553912e83068484b7ab568931ef0e53a6` | `b512dac55391` | 2024-05-07 | build: stop installing from the lockfile |

`git log --diff-filter=AD --format='%h %ad %s' --date=short -- requirements.lock`:

```
b512dac 2024-05-07 build: stop installing from the lockfile
2e8bfe9 2024-04-21 build: install from a fully resolved lockfile
```

**Which releases actually carry the file** (`git cat-file -e <tag>:requirements.lock`):

  - `v2.4.0` -> absent
  - `v2.5.0` -> absent
  - `v2.6.0` -> absent
  - `v2.7.0` -> absent
  - `v2.8.0` -> requirements.lock PRESENT
  - `v2.9.0` -> absent
  - `v2.10.0` -> absent
  - `v2.11.0` -> absent

Exactly **1** release carries it.

Note the second trap here. `git tag --contains 2e8bfe913ce3` reports four
tags, because the commit that ADDED the file is an ancestor of all of them:

```
v2.8.0 v2.9.0 v2.10.0 v2.11.0 
```

Containment of the commit is not presence of the file. Only the tag between the
add and the delete has it.

botocore's pin in the lockfile, at the one release that has it:

```
botocore==1.34.51
```

Lines in the lockfile: **19**, versus
5 direct requirements and
4 constraints.

The Makefile install target follows the lockfile in and out:

```
install:
	pip install -r requirements.lock
```
```
install:
	pip install -r requirements.txt -c constraints.txt
```

## The decoy — a pin edit that changes no version

| field | value |
|---|---|
| full SHA | `d85a5a885e1ca3bac57dc341ffc1696e33fdfa21` |
| short | `d85a5a885e1c` |
| date | 2024-05-15 |
| subject | deps: tidy up constraints.txt |

`git show --numstat --format= d85a5a885e1c`:

```
9	4	constraints.txt
```

`git show --format= d85a5a885e1c`:

```
diff --git a/constraints.txt b/constraints.txt
index 820987e..6917e85 100644
--- a/constraints.txt
+++ b/constraints.txt
@@ -1,4 +1,9 @@
-urllib3==1.26.18
-numpy==1.26.4
-six==1.16.0
-pytz==2024.1
+# Transitive constraints. Sorted; keep it that way so the audit diff is
+# readable. Applied with -c on every install.
+#
+# urllib3 is held on the 1.26 series because the vendored TLS shim in our
+# base image has not been rebuilt against 2.x yet.
+numpy == 1.26.4
+pytz == 2024.1
+six == 1.16.0
+urllib3 == 1.26.18
```

Constraint set before and after, reduced to name==version with whitespace
stripped:

```
before: numpy==1.26.4 pytz==2024.1 six==1.16.0 urllib3==1.26.18 
after:  numpy==1.26.4 pytz==2024.1 six==1.16.0 urllib3==1.26.18 
identical: YES
```

It lands two commits before the pandas loosening and reads like a dependency
change. It is not one.

## Full commit list

`git log --format='%h %ad %s' --date=short --reverse`:

```
dac806a 2024-01-08 Initial import of metrics-etl
ee8588c 2024-01-12 frame: add the dataframe normaliser
19fa25a 2024-01-16 tests: cover the frame normaliser
04e4276 2024-01-20 sink: add the partitioned parquet sink
f7500ea 2024-01-24 build: describe the resolved-set audit snapshot
ee7b7e4 2024-01-28 docs: add a changelog for 2.4.0
cf7d282 2024-02-01 release: 2.4.0
6290535 2024-02-05 cli: add a --dry-run mode
eb01c43 2024-02-09 frame: coerce timestamp columns to UTC
d90cf6d 2024-02-13 cli: add a --partition-by flag
8360102 2024-02-17 tests: cover the UTC coercion
aa66d67 2024-02-21 docs: changelog for 2.5.0
abff643 2024-02-25 release: 2.5.0
6bac38f 2024-02-29 sink: retry the multipart completion on a transient failure
5d1f7b9 2024-03-04 docs: README section on running an export by hand
d439a93 2024-03-08 tests: cover the partition-by flag
e21c6d7 2024-03-12 docs: changelog for 2.6.0
25c660c 2024-03-16 release: 2.6.0
64be895 2024-03-20 frame: drop all-null columns before write
5d36fb5 2024-03-24 cli: honour METRICS_ETL_PROFILE
25cd129 2024-03-28 tests: cover the all-null column drop
3b5e62f 2024-04-01 docs: changelog for 2.7.0
7b3f5ef 2024-04-05 release: 2.7.0
e8e0220 2024-04-09 sink: put the run id in the object key
2e7ea03 2024-04-13 frame: keep column order stable across runs
4529aa1 2024-04-17 tests: cover stable column order
2e8bfe9 2024-04-21 build: install from a fully resolved lockfile
5111c21 2024-04-25 cli: report the recorded dependency set on --version
8ed1c50 2024-04-29 docs: changelog for 2.8.0
ba62cff 2024-05-03 release: 2.8.0
b512dac 2024-05-07 build: stop installing from the lockfile
5c170cc 2024-05-11 tests: trim the frame fixtures
d85a5a8 2024-05-15 deps: tidy up constraints.txt
aa730ca 2024-05-19 deps: loosen the pandas pin
03a58ab 2024-05-23 frame: switch the rollup path to copy-on-write
f02ede7 2024-05-27 tests: cover the copy-on-write switch
a93d8b0 2024-05-31 docs: changelog for 2.9.0
aeba6ea 2024-06-04 release: 2.9.0
2c2eaed 2024-06-08 cli: add --max-rows
fe15de6 2024-06-12 cli: add a --quiet flag
b9b4715 2024-06-16 frame: faster groupby on the rollup path
10e75e5 2024-06-20 tests: cover --max-rows
42eacd4 2024-06-24 docs: changelog for 2.10.0
da8975c 2024-06-28 release: 2.10.0
c677d81 2024-07-02 cli: tidy up the help text
3056ccb 2024-07-06 docs: record the nightly export failure
527ec56 2024-07-10 sink: turn the completion failure into a legible error
10d0172 2024-07-14 frame: memoise the schema lookup
099b9f2 2024-07-18 docs: changelog for 2.11.0
621f89a 2024-07-22 release: 2.11.0
0cecf72 2024-07-26 tests: cover the rollup sum
6d120f7 2024-07-30 docs: README note on the audit snapshot
```
