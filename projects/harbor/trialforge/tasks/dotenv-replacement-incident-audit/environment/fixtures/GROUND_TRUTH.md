# Author-only fixture ground truth

This file is produced by the independent validator and is never copied into the runtime image.

## Counts

- Workspaces: 64
- Potentially exposed: 52
- Logical operations: 174
- Attempts: 180
- Retries: 6
- Affected: 20
- Exposed but unaffected: 32
- Candidate workspaces: 12

## Derived impact sets

- existing_link_overwrite: WS-0002, WS-0004, WS-0007, WS-0011
- broken_link_creation: WS-0003, WS-0009, WS-0013
- race_overwrite: WS-0018, WS-0027
- new_file_0644: WS-0004, WS-0006, WS-0010, WS-0012, WS-0017, WS-0024, WS-0029
- existing_mode_changed: WS-0018, WS-0020, WS-0035, WS-0048
- source_moved: WS-0044, WS-0048, WS-0051

## Machine-readable read-back

```json
{
  "affected": [
    "WS-0002",
    "WS-0003",
    "WS-0004",
    "WS-0006",
    "WS-0007",
    "WS-0009",
    "WS-0010",
    "WS-0011",
    "WS-0012",
    "WS-0013",
    "WS-0017",
    "WS-0018",
    "WS-0020",
    "WS-0024",
    "WS-0027",
    "WS-0029",
    "WS-0035",
    "WS-0044",
    "WS-0048",
    "WS-0051"
  ],
  "allocation": {
    "v0.8.0": 16,
    "v0.8.1": 14,
    "v0.9.0": 12,
    "v0.9.1": 10,
    "v1.0.0-rc1": 12
  },
  "artifact_sha256": {
    "dotenv-replacement-internal.bundle": "ce8e7aeaac2dfe74edc71d686582391a35dcf45cb9d6c4eb0833e9e9526bb7eb",
    "incident.db": "dcd1ba05a240f0deaa096e56418cb8afe6eaa6a9bf8375c6635aad1802f5a4e4",
    "python-dotenv-upstream.bundle": "ea4bfa5098d8a7ff8c68e87b37b280b0c08a087b8ebda82b3c811a5d9d41ef6e"
  },
  "attempts": 180,
  "canaries": {
    "broken_link": [
      "WS-0055",
      "WS-0056"
    ],
    "existing_0640": [
      "WS-0059",
      "WS-0060"
    ],
    "existing_link": [
      "WS-0053",
      "WS-0054"
    ],
    "new_0600": [
      "WS-0057",
      "WS-0058"
    ],
    "unreadable_source": [
      "WS-0061",
      "WS-0062"
    ]
  },
  "derived": {
    "broken_link_creation": [
      "WS-0003",
      "WS-0009",
      "WS-0013"
    ],
    "existing_link_overwrite": [
      "WS-0002",
      "WS-0004",
      "WS-0007",
      "WS-0011"
    ],
    "existing_mode_changed": [
      "WS-0018",
      "WS-0020",
      "WS-0035",
      "WS-0048"
    ],
    "new_file_0644": [
      "WS-0004",
      "WS-0006",
      "WS-0010",
      "WS-0012",
      "WS-0017",
      "WS-0024",
      "WS-0029"
    ],
    "race_overwrite": [
      "WS-0018",
      "WS-0027"
    ],
    "source_moved": [
      "WS-0044",
      "WS-0048",
      "WS-0051"
    ]
  },
  "exposed_unaffected": [
    "WS-0001",
    "WS-0005",
    "WS-0008",
    "WS-0014",
    "WS-0015",
    "WS-0016",
    "WS-0019",
    "WS-0021",
    "WS-0022",
    "WS-0023",
    "WS-0025",
    "WS-0026",
    "WS-0028",
    "WS-0030",
    "WS-0031",
    "WS-0032",
    "WS-0033",
    "WS-0034",
    "WS-0036",
    "WS-0037",
    "WS-0038",
    "WS-0039",
    "WS-0040",
    "WS-0041",
    "WS-0042",
    "WS-0043",
    "WS-0045",
    "WS-0046",
    "WS-0047",
    "WS-0049",
    "WS-0050",
    "WS-0052"
  ],
  "operations": 174,
  "retries": 6,
  "safe_candidate": [
    "WS-0053",
    "WS-0054",
    "WS-0055",
    "WS-0056",
    "WS-0057",
    "WS-0058",
    "WS-0059",
    "WS-0060",
    "WS-0061",
    "WS-0062",
    "WS-0063",
    "WS-0064"
  ],
  "tags": {
    "prod-2026-08-17": "80df87e01dbec08d92730002064f127993619a07",
    "replace-v0.8.0": "efa34cf858d01609cdf8bf961ec6553fb16749be",
    "replace-v0.8.1": "6a28bba2af74af9c7220878ef797a99ce6ad4132",
    "replace-v0.9.0": "eb4d087101e6c757e550a1b5d2ae67c5e77e5a2b",
    "replace-v0.9.1": "62c02c2ae9811966818b75233b82bac71c6079b3",
    "replace-v1.0.0-rc1": "583042510c83c9a7816162407148e6fdab58d688"
  }
}
```
