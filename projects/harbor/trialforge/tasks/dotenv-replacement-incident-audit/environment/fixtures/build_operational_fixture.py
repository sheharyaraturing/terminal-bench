#!/usr/bin/env python3
"""Build the deterministic fictional incident database, logs, and receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


CUTOFF = "2026-08-17T18:00:00Z"
BASE_TIME = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)

DIGESTS = {
    "v0.8.0": "sha256:a79d834d437639db0f4a09dcd0cc76e3a48d7c29190c37001f374a0671f40a28",
    "v0.8.1": "sha256:250581914b29e5be60cbb7b346115f632b9984b4b7459c5c206d55eeaa6e8124",
    "v0.9.0": "sha256:8265338c0fc43070b8fb4364fb7eb653f85c8c082a1e252805d416a9ebea05a4",
    "v0.9.1": "sha256:45541b8b7f3bc36a0393fd4fec0dfc3a15dcc10be7e988eff19fd4eb2a36dd32",
    "v1.0.0-rc1": "sha256:d0f157e5480991b9bb3dab96b98645009d038bc0ab7b60bcc7111883961ec8ca",
}

# Seven assigned v0.9.1 workspaces had no requested replacement before the
# cutoff. That distinction is intentional: assignment exposure is not impact.
NO_OPERATION_WORKSPACES = {43, 45, 46, 47, 49, 50, 52}

EXISTING_LINK = {2, 4, 7, 11}
BROKEN_LINK = {3, 9, 13}
RACE_OVERWRITE = {18, 27}
NEW_0644 = {4, 6, 10, 12, 17, 24, 29}
MODE_CHANGED = {18, 20, 35, 48}
SOURCE_MOVED = {44, 48, 51}

RETRY_CASES = {(5, 1), (16, 2), (23, 3), (32, 1), (41, 2), (58, 3)}

STALE_LABELS = {
    2: "v0.8.1",
    18: "v0.8.0",
    35: "v0.9.1",
    44: "v0.9.0",
    53: "v0.9.1",
    60: "v0.9.0",
}


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def workspace_id(number: int) -> str:
    return f"WS-{number:04d}"


def release_for(number: int) -> str:
    if number <= 16:
        return "v0.8.0"
    if number <= 30:
        return "v0.8.1"
    if number <= 42:
        return "v0.9.0"
    if number <= 52:
        return "v0.9.1"
    return "v1.0.0-rc1"


def default_target_mode(release: str) -> str:
    return {
        "v0.8.0": "0600",
        "v0.8.1": "0644",
        "v0.9.0": "0600",
        "v0.9.1": "0644",
        "v1.0.0-rc1": "0600",
    }[release]


def build_operations() -> list[dict[str, object]]:
    operations: list[dict[str, object]] = []
    sequence = 0
    for number in range(1, 65):
        if number in NO_OPERATION_WORKSPACES:
            continue
        per_workspace = 4 if number <= 3 else 3
        for ordinal in range(1, per_workspace + 1):
            sequence += 1
            ws = workspace_id(number)
            release = release_for(number)
            operations.append(
                {
                    "sequence": sequence,
                    "operation_id": f"OP-{sequence:04d}",
                    "ordinal": ordinal,
                    "workspace_number": number,
                    "workspace_id": ws,
                    "release": release,
                    "image_digest": DIGESTS[release],
                    "requested_at": iso(BASE_TIME + timedelta(seconds=sequence * 19)),
                    "source_path": f"/srv/workspaces/{ws}/incoming/replacement-{ordinal}.env",
                    "target_path": f"/srv/workspaces/{ws}/secrets/runtime-{ordinal}.env",
                }
            )
    assert len(operations) == 174
    return operations


def preflight(operation: dict[str, object]) -> dict[str, object | None]:
    number = int(operation["workspace_number"])
    ordinal = int(operation["ordinal"])
    release = str(operation["release"])
    op_id = str(operation["operation_id"])

    observation: dict[str, object | None] = {
        "source_state": "regular",
        "source_sha256": digest(f"{op_id}:source"),
        "source_mode": "0644",
        "source_readable": 1,
        "target_kind": "regular",
        "target_mode": default_target_mode(release),
        "target_sha256": digest(f"{op_id}:target-before"),
        "referent_path": None,
        "referent_sha256": None,
    }

    if ordinal == 1 and number in EXISTING_LINK:
        observation.update(
            target_kind="symlink",
            target_mode=None,
            target_sha256=None,
            referent_path=f"/srv/shared/managed/{workspace_id(number)}.env",
            referent_sha256=digest(f"{op_id}:referent-before"),
        )
    elif ordinal == 1 and number in BROKEN_LINK:
        observation.update(
            target_kind="broken_symlink",
            target_mode=None,
            target_sha256=None,
            referent_path=f"/srv/shared/missing/{workspace_id(number)}.env",
            referent_sha256=None,
        )
    elif ordinal == 1 and number in RACE_OVERWRITE:
        observation.update(target_kind="regular", target_mode="0644")
    elif (number == 4 and ordinal == 2) or (number in NEW_0644 - {4} and ordinal == 1):
        observation.update(target_kind="missing", target_mode=None, target_sha256=None)
    elif (number == 18 and ordinal == 2) or (number in MODE_CHANGED - {18} and ordinal == 1):
        observation.update(target_kind="regular", target_mode="0640")

    # Candidate canaries exercise each contract edge without changing anything
    # outside the target directory or losing source data.
    if release == "v1.0.0-rc1" and ordinal == 1:
        if number in {53, 54}:
            observation.update(
                target_kind="symlink",
                target_mode=None,
                target_sha256=None,
                referent_path=f"/srv/shared/canary/{workspace_id(number)}.env",
                referent_sha256=digest(f"{op_id}:canary-referent"),
            )
        elif number in {55, 56}:
            observation.update(
                target_kind="broken_symlink",
                target_mode=None,
                target_sha256=None,
                referent_path=f"/srv/shared/canary-missing/{workspace_id(number)}.env",
                referent_sha256=None,
            )
        elif number in {57, 58}:
            observation.update(target_kind="missing", target_mode=None, target_sha256=None)
        elif number in {59, 60}:
            observation.update(target_kind="regular", target_mode="0640")
        elif number in {61, 62}:
            observation.update(
                source_state="unreadable",
                source_mode="0000",
                source_readable=0,
                target_kind="regular",
                target_mode="0640",
            )

    return observation


def terminal_receipt(
    operation: dict[str, object], observation: dict[str, object | None]
) -> tuple[dict[str, object | None], str]:
    number = int(operation["workspace_number"])
    ordinal = int(operation["ordinal"])
    release = str(operation["release"])
    op_id = str(operation["operation_id"])
    source_hash = observation["source_sha256"]

    receipt: dict[str, object | None] = {
        "operation_id": op_id,
        "workspace_id": operation["workspace_id"],
        "completed_at": iso(BASE_TIME + timedelta(seconds=9000 + int(operation["sequence"]) * 23)),
        "status": "success",
        "image_digest": operation["image_digest"],
        "worker_release_label": STALE_LABELS.get(number, release),
        "source_state_after": observation["source_state"],
        "source_sha256_after": source_hash,
        "source_mode_after": observation["source_mode"],
        "target_kind_after": observation["target_kind"],
        "target_mode_after": observation["target_mode"],
        "target_sha256_after": observation["target_sha256"],
        "observed_referent_path": observation["referent_path"],
        "observed_referent_sha256_after": observation["referent_sha256"],
    }

    if not observation["source_readable"]:
        receipt["status"] = "source_error"
        return receipt, "source_read_denied_target_unchanged"

    if release == "v0.8.0":
        if observation["target_kind"] == "symlink":
            receipt["observed_referent_sha256_after"] = source_hash
            detail = "destination_kind=symlink write=committed"
        elif observation["target_kind"] == "broken_symlink":
            receipt["target_kind_after"] = "symlink"
            receipt["observed_referent_sha256_after"] = source_hash
            detail = "destination_kind=broken_symlink write=committed"
        elif observation["target_kind"] == "missing":
            receipt.update(target_kind_after="regular", target_mode_after="0644", target_sha256_after=source_hash)
            detail = "destination_kind=missing write=committed"
        else:
            receipt["target_sha256_after"] = source_hash
            detail = "destination_kind=regular write=committed"
    elif release == "v0.8.1":
        if ordinal == 1 and number in RACE_OVERWRITE:
            receipt.update(
                target_kind_after="symlink",
                target_mode_after=None,
                target_sha256_after=None,
                observed_referent_path=f"/srv/outside/race/{workspace_id(number)}.env",
                observed_referent_sha256_after=source_hash,
            )
            detail = "link_check=regular post_check_kind=symlink write=committed"
        else:
            receipt.update(
                target_kind_after="regular",
                target_mode_after="0644",
                target_sha256_after=source_hash,
                observed_referent_path=observation["referent_path"],
                observed_referent_sha256_after=observation["referent_sha256"],
            )
            detail = f"link_check={observation['target_kind']} write=committed"
    elif release == "v0.9.0":
        receipt.update(
            target_kind_after="regular",
            target_mode_after="0600",
            target_sha256_after=source_hash,
        )
        detail = "temporary_file=created atomic_replace=committed"
    elif release == "v0.9.1":
        receipt.update(
            source_state_after="missing",
            source_sha256_after=None,
            source_mode_after=None,
            target_kind_after="regular",
            target_mode_after=observation["source_mode"],
            target_sha256_after=source_hash,
        )
        detail = "rename_source_to_target=committed"
    else:
        target_mode = observation["target_mode"] if observation["target_kind"] == "regular" else "0600"
        receipt.update(
            target_kind_after="regular",
            target_mode_after=target_mode,
            target_sha256_after=source_hash,
        )
        detail = "rewrite_transaction=committed"

    return receipt, detail


SCHEMA = """
PRAGMA page_size = 4096;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE workspaces (
    workspace_id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    service_tier TEXT NOT NULL,
    owner_team TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE deployment_assignments (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(workspace_id),
    image_digest TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    incident_cutoff TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE replacement_operations (
    operation_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    requested_at TEXT NOT NULL,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE preflight_observations (
    operation_id TEXT PRIMARY KEY REFERENCES replacement_operations(operation_id),
    source_state TEXT NOT NULL,
    source_sha256 TEXT,
    source_mode TEXT,
    source_readable INTEGER NOT NULL CHECK (source_readable IN (0, 1)),
    target_kind TEXT NOT NULL,
    target_mode TEXT,
    target_sha256 TEXT,
    referent_path TEXT,
    referent_sha256 TEXT
) WITHOUT ROWID;

CREATE TABLE attempt_registry (
    attempt_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES replacement_operations(operation_id),
    attempt_number INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    worker_log_file TEXT NOT NULL,
    worker_log_line INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    result TEXT NOT NULL,
    UNIQUE (operation_id, attempt_number)
) WITHOUT ROWID;

CREATE TABLE receipt_index (
    operation_id TEXT PRIMARY KEY REFERENCES replacement_operations(operation_id),
    receipt_file TEXT NOT NULL,
    receipt_line INTEGER NOT NULL,
    completed_at TEXT NOT NULL
) WITHOUT ROWID;
"""


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for directory_name in ("logs", "receipts"):
        directory = output / directory_name
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir()
    database = output / "incident.db"
    if database.exists():
        database.unlink()

    operations = build_operations()
    preflights: dict[str, dict[str, object | None]] = {}
    receipts: dict[str, dict[str, object | None]] = {}
    details: dict[str, str] = {}
    for operation in operations:
        op_id = str(operation["operation_id"])
        observation = preflight(operation)
        receipt, detail = terminal_receipt(operation, observation)
        preflights[op_id] = observation
        receipts[op_id] = receipt
        details[op_id] = detail

    receipt_files: dict[int, list[dict[str, object | None]]] = {worker: [] for worker in range(1, 7)}
    receipt_locations: dict[str, tuple[str, int]] = {}
    for operation in operations:
        op_id = str(operation["operation_id"])
        file_number = (int(operation["sequence"]) - 1) % 6 + 1
        receipt_files[file_number].append(receipts[op_id])
        receipt_locations[op_id] = (f"receipt-{file_number:02d}.jsonl", len(receipt_files[file_number]))

    for file_number, rows in receipt_files.items():
        path = output / "receipts" / f"receipt-{file_number:02d}.jsonl"
        path.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
            newline="\n",
        )
        assert len(rows) == 29

    attempt_rows: list[tuple[object, ...]] = []
    worker_lines: dict[int, list[str]] = {worker: [] for worker in range(1, 7)}
    attempt_sequence = 0
    for operation in operations:
        number = int(operation["workspace_number"])
        ordinal = int(operation["ordinal"])
        op_id = str(operation["operation_id"])
        has_retry = (number, ordinal) in RETRY_CASES
        attempts_for_operation = 2 if has_retry else 1
        for attempt_number in range(1, attempts_for_operation + 1):
            attempt_sequence += 1
            attempt_id = f"ATT-{attempt_sequence:04d}"
            worker_number = (attempt_sequence - 1) % 6 + 1
            worker_id = f"worker-{worker_number:02d}"
            started = iso(BASE_TIME + timedelta(seconds=5000 + attempt_sequence * 17))
            transient = has_retry and attempt_number == 1
            result = "transient_error" if transient else str(receipts[op_id]["status"])
            detail = "lease_lost_before_commit" if transient else details[op_id]
            log_line = (
                f"{started} attempt={attempt_id} operation={op_id} "
                f"workspace={operation['workspace_id']} image={operation['image_digest']} "
                f"attempt_no={attempt_number} result={result} detail=\"{detail}\""
            )
            worker_lines[worker_number].append(log_line)
            attempt_rows.append(
                (
                    attempt_id,
                    op_id,
                    attempt_number,
                    worker_id,
                    f"worker-{worker_number:02d}.log",
                    len(worker_lines[worker_number]),
                    started,
                    result,
                )
            )

    assert attempt_sequence == 180
    for worker_number, lines in worker_lines.items():
        assert len(lines) == 30
        (output / "logs" / f"worker-{worker_number:02d}.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )

    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?)",
        [
            (
                workspace_id(number),
                ("us-east", "eu-west", "ap-south", "us-west")[(number - 1) % 4],
                ("standard", "regulated", "critical")[(number - 1) % 3],
                f"platform-{(number - 1) % 8 + 1:02d}",
            )
            for number in range(1, 65)
        ],
    )
    connection.executemany(
        "INSERT INTO deployment_assignments VALUES (?, ?, ?, ?)",
        [
            (
                workspace_id(number),
                DIGESTS[release_for(number)],
                iso(BASE_TIME - timedelta(days=8 - ((number - 1) % 8), minutes=number)),
                CUTOFF,
            )
            for number in range(1, 65)
        ],
    )
    connection.executemany(
        "INSERT INTO replacement_operations VALUES (?, ?, ?, ?, ?)",
        [
            (
                operation["operation_id"],
                operation["workspace_id"],
                operation["requested_at"],
                operation["source_path"],
                operation["target_path"],
            )
            for operation in operations
        ],
    )
    connection.executemany(
        "INSERT INTO preflight_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                operation["operation_id"],
                preflights[str(operation["operation_id"])]["source_state"],
                preflights[str(operation["operation_id"])]["source_sha256"],
                preflights[str(operation["operation_id"])]["source_mode"],
                preflights[str(operation["operation_id"])]["source_readable"],
                preflights[str(operation["operation_id"])]["target_kind"],
                preflights[str(operation["operation_id"])]["target_mode"],
                preflights[str(operation["operation_id"])]["target_sha256"],
                preflights[str(operation["operation_id"])]["referent_path"],
                preflights[str(operation["operation_id"])]["referent_sha256"],
            )
            for operation in operations
        ],
    )
    connection.executemany("INSERT INTO attempt_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?)", attempt_rows)
    connection.executemany(
        "INSERT INTO receipt_index VALUES (?, ?, ?, ?)",
        [
            (
                operation["operation_id"],
                receipt_locations[str(operation["operation_id"])][0],
                receipt_locations[str(operation["operation_id"])][1],
                receipts[str(operation["operation_id"])]["completed_at"],
            )
            for operation in operations
        ],
    )
    connection.commit()
    connection.execute("VACUUM")
    connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
