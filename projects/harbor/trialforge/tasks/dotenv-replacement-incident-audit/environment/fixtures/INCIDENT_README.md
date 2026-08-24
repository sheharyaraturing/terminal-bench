# Dotenv replacement incident evidence

This directory is a fixed, fictional incident snapshot for the cutoff recorded in
the `deployment_assignments` table. It is not connected to a real company or live
deployment.

Evidence is deliberately split:

- `/data/repos/dotenv-replacement-internal` contains the command history,
  replacement contract, release tags, and image manifest.
- `incident.db` contains workspace assignments, preflight observations, the
  attempt registry, and receipt locations.
- `logs/` contains one line per worker attempt, including retries.
- `receipts/` contains one terminal outcome per logical operation.

Times are UTC. File modes are four-digit octal strings. A blank hash means the
path did not contain a regular file at that observation point. Worker attempts
are not logical operations: use the operation and attempt identifiers when
reconciling retries.
