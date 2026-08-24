# Segment Growth v2 — Planning Restatement Benchmark

This bundle is a harder, deterministic redesign of the original segment-growth task.

## Agent-visible task inputs
- `instruction.md`
- `segments.xlsx` (`RawData` + active `Methodology`)
- `segment_master.csv`
- `restatements.csv`
- `planning_config.json`
- `source_manifest.json`
- `archive/` and `notes/` contain plausible but explicitly non-authoritative distractors

## Author-only validation assets
- `solution/solve.py` — generic reference implementation
- `solution/solve.sh` — LF-normalized shell launcher
- `tests/expected/growth.xlsx` — expected output
- `tests/artifacts/`, `tests/shape/`, `tests/growth/`, and `tests/undefined/` — deterministic RewardKit checks

## Failure modes intentionally covered
1. Wrong file/source authority
2. RawData order copied instead of master order
3. Name-based join instead of SegmentID join
4. Master-only and RawData-only segment handling
5. Approved/latest/as-of restatement selection
6. Blank restatement that removes a value
7. Zero vs missing semantics
8. Negative revenue and class-specific formulas
9. Segment-year override precedence
10. ROUND_HALF_UP boundary cases
11. Required output years independent of RawData availability
12. Archived methodology/output distractors

The reference solution is data-driven: it reads the active methodology, configuration, master data, and restatements rather than hardcoding expected cells.
