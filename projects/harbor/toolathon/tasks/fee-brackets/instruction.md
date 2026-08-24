The balance snapshot in `accounts.csv` needs its account maintenance fees run.

`policy/` holds the fee schedule that governs the run.

Produce two files in the workspace root:

- `fee_schedule_run.xlsx` — a worksheet named `Fees` whose columns are `Account`, `Balance`, `Fee` and `EffectiveRate`, in that order, with one row per account in the run.
- `workings.json` — the run's supporting figures, in the shape the schedule sets out.
