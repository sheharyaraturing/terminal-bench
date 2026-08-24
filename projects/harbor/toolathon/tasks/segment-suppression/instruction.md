The conversion review needs its segment table.

`metrics/Definitions.md` is the authority on how the metric is computed. The source extracts are under `data/`.

Produce two files in the workspace root:

- `conversion_by_segment.xlsx` — a sheet named `Conversion`, with the columns `Segment`, `Numerator`, `Denominator`, `Rate` and `ReasonCode` in that order.
- `workings.json` — the workings file the definitions call for.
