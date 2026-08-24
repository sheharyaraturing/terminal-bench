# Cast-regression audit against a real repository

**Persona:** Data Platform Engineer
**Archetype:** commit-forensics -> quantified data impact
**Targets:** ~52 tool calls · 15 claims · 8 servers declared, 26 tools exposed

Unlike the other tasks in this suite, the ground truth here is already written. Everything
in `tests/reward.toml` was derived from the pinned bundle and the eight baked CSVs, and the
derivation is recorded below so a reviewer can reproduce it rather than trust it.

## The premise

`environment/fixtures/agate.bundle` is a full-history bundle of `wireservice/agate`, pinned at
`7aa490cbc3d965e0a950dd904ea1f9cf5ced013c` (1,611 commits, 43 tags). The Dockerfile clones it
to `/data/repos/agate` and checks out that SHA as branch `main`.

agate is the type-inference engine underneath csvkit: `Number.test()` decides whether a column
looks numeric, `Number.cast()` converts the values. Three real commits touch how a number is
parsed out of text:

| Commit | Subject | Issue | First release |
|---|---|---|---|
| `fff4714` | Handle percents and currency symbols when casting numbers | #217 | **0.8.0** |
| `ed3b6f8` | Fix stripping currency symbols | #333 | **1.0.1** |
| `d8dfc3a` | Collapse DataType.test | #382 | **1.1.0** |
| `01c0591` | Parse negative currency text as Number | #595 | **1.4.0** |

**The first subject line is wrong, and that is the task.** `fff4714` adds the `CURRENCY_SYMBOLS`
list and the stripping to `test()` only. `cast()` is untouched until `ed3b6f8`. Verified by
reading the file at the tags:

```
0.8.0  cast():  d = d.strip()
1.0.0  cast():  d = d.strip()
1.0.1  cast():  d = d.strip(); d = d.strip('%'); for symbol in CURRENCY_SYMBOLS: d = d.strip(symbol)
```

So across **0.8.0, 0.9.0, 0.10.0, 0.11.0 and 1.0.0** — five releases — a currency column is
inferred numeric and then raises a cast error on every row. The prompt pins the loader at 0.9.0,
inside that window.

`d8dfc3a` is the epilogue: it deletes `Number.test()` outright (zero occurrences at 1.1.0) and
replaces the per-type test methods with one generic `DataType.test()` that simply calls
`self.cast()`. From 1.1.0 the two cannot disagree by construction: 1.0.1 patched the symptom,
while 1.1.0 removed the possibility.

The CHANGELOG repeats the misleading "when casting" wording under the 0.8.0 section, so an agent
that reads release notes instead of diffs reaches the wrong answer twice over.

## Difficulty design

Three traps, all naturally occurring — none planted:

1. **Subject line vs diff.** Both the commit message and the CHANGELOG entry for #217 claim to fix
   casting. Only the diff shows it did not.
2. **Lexical vs semantic version ordering.** Listing tags containing a commit yields string order,
   so #217 appears to start at `0.10.0` and #595 at `1.10.0`. Both wrong.
3. **Two decoy columns.** `Top Movies.Gross` (`$28.34M`) and `fantasy sports.Salary(USD)` (`$4M`)
   look like money but carry a magnitude suffix, so `test()` rejects them and they are never in the
   numeric set on any version. A `$`-grep overcounts.

There is no `git_tag` tool on the git server — the commit-to-release mapping has to come from the
CHANGELOG or from shelling out. That is deliberate; it is the step where weaker agents stall.

## Derivation of the numbers

Applying `test()` and each release's `cast()` across all eight CSVs (agate's `test`/`cast` logic
reimplemented from the diffs, `babel.numbers.parse_decimal` with `en_US`):

| CSV | Column | Rows | Fail @0.9.0 | Fail @1.0.1 |
|---|---|---:|---:|---:|
| Barber Shop.csv | Price | 31 | 31 | 0 |
| Pet Care 2023 Weekly Financials.csv | Daily Care Weekly Revenue | 52 | 52 | 0 |
| Pet Care 2023 Weekly Financials.csv | Grooming Services Weekly Revenue | 52 | 52 | 0 |
| Pet Care 2023 Weekly Financials.csv | Training Services Weekly Revenue | 52 | 52 | 0 |
| Pet Care 2023 Weekly Financials.csv | Total Weekly Revenue  Week | 52 | 52 | 0 |
| Pet Care 2023 Weekly Financials.csv | Total Weekly Expenses | 52 | 52 | 0 |
| Pet Care 2023 Weekly Financials.csv | Weekly Profits | 52 | 52 | 0 |

**7 columns, 343 cells** (31 + 6x52). Negative currency values across all eight CSVs: **0**, so
#595 is a genuine no-op here.

### The warehouse is a decoy, verified against the real image

Probed `/data/db/turing.db` inside a live `turing-mcpatlas:0.0.1` container: 8 tables, 480 rows,
and **all 72 columns are declared TEXT**. Nothing is numeric anywhere. The seven affected columns
are therefore typed identically to columns that convert cleanly, and the schema is not evidence of
the regression in either direction — whatever writes that database ignores inferred types entirely.

The claim was originally worded as "the affected columns are stored as text", which any agent that
looks at any schema satisfies for free. It now requires noticing the typing is uniform and refusing
the tempting inference, which is the discriminating version of the same observation.

## Why `[environment]` has no `docker_image`

`harbor.environments.definition.should_use_prebuilt_docker_image()` returns `True` whenever
`docker_image` is set and `--force-build` is absent, which skips `environment/Dockerfile`
entirely. This task's premise is the repository that Dockerfile clones in, so a prebuilt pull
would hand the agent an empty `/data/repos`. The key is omitted on purpose — do not add it back.
