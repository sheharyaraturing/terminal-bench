#!/usr/bin/env python3
"""Independent read-back validator for the emitted incident artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import tempfile
import tomllib
from collections import Counter, defaultdict
from pathlib import Path


PINNED = "751f8c148222e58aa173c83c4e5e6cfccb2cc124"
EXPECTED_TABLES = {
    "workspaces",
    "deployment_assignments",
    "replacement_operations",
    "preflight_observations",
    "attempt_registry",
    "receipt_index",
}
EXPECTED_ALLOCATION = {
    "v0.8.0": 16,
    "v0.8.1": 14,
    "v0.9.0": 12,
    "v0.9.1": 10,
    "v1.0.0-rc1": 12,
}
EXPECTED = {
    "existing_link_overwrite": {"WS-0002", "WS-0004", "WS-0007", "WS-0011"},
    "broken_link_creation": {"WS-0003", "WS-0009", "WS-0013"},
    "race_overwrite": {"WS-0018", "WS-0027"},
    "new_file_0644": {"WS-0004", "WS-0006", "WS-0010", "WS-0012", "WS-0017", "WS-0024", "WS-0029"},
    "existing_mode_changed": {"WS-0018", "WS-0020", "WS-0035", "WS-0048"},
    "source_moved": {"WS-0044", "WS-0048", "WS-0051"},
}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(*command: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def git_evidence(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    internal_bundle = root / "bundles" / "dotenv-replacement-internal.bundle"
    upstream_bundle = root / "bundles" / "python-dotenv-upstream.bundle"
    assert internal_bundle.is_file() and upstream_bundle.is_file()

    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        upstream = temporary_path / "upstream"
        internal = temporary_path / "internal"
        run("git", "clone", str(upstream_bundle), str(upstream))
        assert run("git", "rev-parse", "HEAD", cwd=upstream) == PINNED
        license_text = (upstream / "LICENSE").read_text(encoding="utf-8")
        assert "Redistribution and use in source and binary forms" in license_text
        assert "Neither the name of django-dotenv" in license_text

        run("git", "clone", str(internal_bundle), str(internal))
        assert run("git", "rev-parse", "prod-2026-08-17", cwd=internal)
        tags = {
            tag: run("git", "rev-parse", tag, cwd=internal)
            for tag in (
                "replace-v0.8.0",
                "replace-v0.8.1",
                "replace-v0.9.0",
                "replace-v0.9.1",
                "replace-v1.0.0-rc1",
                "prod-2026-08-17",
            )
        }
        assert len(set(tags.values())) == 6
        assert int(run("git", "rev-list", "--count", f"{PINNED}..prod-2026-08-17", cwd=internal)) == 6

        source_by_tag = {
            tag: run("git", "show", f"{tag}:src/dotenv/replacement.py", cwd=internal)
            for tag in tags
            if tag.startswith("replace-")
        }
        assert 'open(target, "w"' in source_by_tag["replace-v0.8.0"]
        assert "os.path.lexists(target)" in source_by_tag["replace-v0.8.1"]
        assert "os.unlink(target)" in source_by_tag["replace-v0.8.1"]
        assert "tempfile.mkstemp" in source_by_tag["replace-v0.9.0"]
        assert "os.replace(temporary, target)" in source_by_tag["replace-v0.9.0"]
        assert "os.replace(source, target)" in source_by_tag["replace-v0.9.1"]
        assert "with rewrite(target" in source_by_tag["replace-v1.0.0-rc1"]

        notice = run("git", "show", "prod-2026-08-17:INTERNAL_FORK_NOTICE.md", cwd=internal)
        assert "fictional" in notice.lower() and PINNED in notice
        contract = run("git", "show", "prod-2026-08-17:docs/replacement-contract.md", cwd=internal)
        for phrase in ("transactionally", "SOURCE remains", "keeps its established", "mode `0600`"):
            assert phrase in contract

        manifest_bytes = subprocess.run(
            ["git", "show", "prod-2026-08-17:deploy/image-manifest.toml"],
            cwd=internal,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
        assert manifest["cutoff"] == "2026-08-17T18:00:00Z"
        digest_to_release = {row["digest"]: row["release"] for row in manifest["image"]}
        assert len(digest_to_release) == 5
        return digest_to_release, tags


def read_receipts(root: Path) -> tuple[dict[str, dict[str, object]], dict[tuple[str, int], str]]:
    receipts: dict[str, dict[str, object]] = {}
    location_to_operation: dict[tuple[str, int], str] = {}
    files = sorted((root / "receipts").glob("receipt-*.jsonl"))
    assert len(files) == 6
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 29
        for line_number, line in enumerate(lines, 1):
            row = json.loads(line)
            operation_id = row["operation_id"]
            assert operation_id not in receipts
            receipts[operation_id] = row
            location_to_operation[(path.name, line_number)] = operation_id
    assert len(receipts) == 174
    return receipts, location_to_operation


def read_logs(root: Path) -> dict[tuple[str, int], str]:
    attempt_pattern = re.compile(r"\battempt=(ATT-\d{4})\b")
    result: dict[tuple[str, int], str] = {}
    seen: set[str] = set()
    files = sorted((root / "logs").glob("worker-*.log"))
    assert len(files) == 6
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 30
        for line_number, line in enumerate(lines, 1):
            match = attempt_pattern.search(line)
            assert match, (path, line_number)
            attempt_id = match.group(1)
            assert attempt_id not in seen
            seen.add(attempt_id)
            result[(path.name, line_number)] = attempt_id
    assert len(seen) == 180
    return result


def format_ids(values: set[str]) -> str:
    return ", ".join(sorted(values))


def validate(root: Path) -> dict[str, object]:
    digest_to_release, tags = git_evidence(root)
    receipts, receipt_locations = read_receipts(root)
    log_locations = read_logs(root)

    connection = sqlite3.connect(root / "incident.db")
    connection.row_factory = sqlite3.Row
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == EXPECTED_TABLES
    counts = {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in sorted(EXPECTED_TABLES)
    }
    assert counts == {
        "attempt_registry": 180,
        "deployment_assignments": 64,
        "preflight_observations": 174,
        "receipt_index": 174,
        "replacement_operations": 174,
        "workspaces": 64,
    }

    cutoff_rows = connection.execute(
        "SELECT incident_cutoff, COUNT(*) FROM deployment_assignments GROUP BY incident_cutoff"
    ).fetchall()
    assert [tuple(row) for row in cutoff_rows] == [("2026-08-17T18:00:00Z", 64)]

    allocation = Counter()
    workspace_release: dict[str, str] = {}
    for row in connection.execute("SELECT workspace_id, image_digest FROM deployment_assignments"):
        assert row["image_digest"] in digest_to_release
        release = digest_to_release[row["image_digest"]]
        allocation[release] += 1
        workspace_release[row["workspace_id"]] = release
    assert dict(allocation) == EXPECTED_ALLOCATION

    preflight_rows = {
        row["operation_id"]: dict(row)
        for row in connection.execute("SELECT * FROM preflight_observations")
    }
    operation_workspace = {
        row["operation_id"]: row["workspace_id"]
        for row in connection.execute("SELECT operation_id, workspace_id FROM replacement_operations")
    }
    assert set(preflight_rows) == set(receipts) == set(operation_workspace)

    derived: dict[str, set[str]] = defaultdict(set)
    for operation_id, before in preflight_rows.items():
        after = receipts[operation_id]
        workspace = operation_workspace[operation_id]
        assert after["workspace_id"] == workspace
        if (
            before["target_kind"] == "symlink"
            and before["referent_sha256"]
            and after["observed_referent_sha256_after"] != before["referent_sha256"]
        ):
            derived["existing_link_overwrite"].add(workspace)
        if (
            before["target_kind"] == "broken_symlink"
            and before["referent_sha256"] is None
            and after["observed_referent_sha256_after"] is not None
        ):
            derived["broken_link_creation"].add(workspace)
        if (
            before["target_kind"] == "regular"
            and after["target_kind_after"] == "symlink"
            and str(after["observed_referent_path"]).startswith("/srv/outside/race/")
        ):
            derived["race_overwrite"].add(workspace)
        if (
            before["target_kind"] == "missing"
            and after["target_kind_after"] == "regular"
            and after["target_mode_after"] == "0644"
        ):
            derived["new_file_0644"].add(workspace)
        if (
            before["target_kind"] == "regular"
            and after["target_kind_after"] == "regular"
            and before["target_mode"] != after["target_mode_after"]
        ):
            derived["existing_mode_changed"].add(workspace)
        if before["source_sha256"] and after["source_state_after"] == "missing":
            derived["source_moved"].add(workspace)

    assert {key: derived[key] for key in EXPECTED} == EXPECTED
    affected = set().union(*(derived[key] for key in EXPECTED))
    assert len(affected) == 20
    exposed = {ws for ws, release in workspace_release.items() if release != "v1.0.0-rc1"}
    safe_candidate = {ws for ws, release in workspace_release.items() if release == "v1.0.0-rc1"}
    assert len(exposed) == 52 and len(safe_candidate) == 12
    assert affected <= exposed and not (affected & safe_candidate)
    exposed_unaffected = exposed - affected
    assert len(exposed_unaffected) == 32

    attempt_counts = Counter()
    retry_attempts = 0
    for row in connection.execute("SELECT * FROM attempt_registry"):
        attempt_counts[row["operation_id"]] += 1
        assert log_locations[(row["worker_log_file"], row["worker_log_line"])] == row["attempt_id"]
        if row["attempt_number"] > 1:
            retry_attempts += 1
    assert len(attempt_counts) == 174
    assert sum(attempt_counts.values()) == 180
    assert sum(value - 1 for value in attempt_counts.values()) == 6
    assert retry_attempts == 6
    assert sum(value == 2 for value in attempt_counts.values()) == 6

    for row in connection.execute("SELECT * FROM receipt_index"):
        key = (row["receipt_file"], row["receipt_line"])
        assert receipt_locations[key] == row["operation_id"]
        assert receipts[row["operation_id"]]["completed_at"] == row["completed_at"]

    candidate_operations = [
        (operation_id, preflight_rows[operation_id], receipts[operation_id])
        for operation_id, workspace in operation_workspace.items()
        if workspace in safe_candidate
    ]
    canary_sets = {
        "existing_link": {
            operation_workspace[op]
            for op, before, after in candidate_operations
            if before["target_kind"] == "symlink"
            and after["target_kind_after"] == "regular"
            and before["referent_sha256"] == after["observed_referent_sha256_after"]
        },
        "broken_link": {
            operation_workspace[op]
            for op, before, after in candidate_operations
            if before["target_kind"] == "broken_symlink"
            and after["target_kind_after"] == "regular"
            and after["observed_referent_sha256_after"] is None
        },
        "new_0600": {
            operation_workspace[op]
            for op, before, after in candidate_operations
            if before["target_kind"] == "missing" and after["target_mode_after"] == "0600"
        },
        "existing_0640": {
            operation_workspace[op]
            for op, before, after in candidate_operations
            if before["target_kind"] == "regular"
            and before["target_mode"] == "0640"
            and after["target_mode_after"] == "0640"
            and after["status"] == "success"
        },
        "unreadable_source": {
            operation_workspace[op]
            for op, before, after in candidate_operations
            if before["source_readable"] == 0
            and after["status"] == "source_error"
            and before["target_sha256"] == after["target_sha256_after"]
            and before["target_mode"] == after["target_mode_after"]
        },
    }
    assert canary_sets == {
        "existing_link": {"WS-0053", "WS-0054"},
        "broken_link": {"WS-0055", "WS-0056"},
        "new_0600": {"WS-0057", "WS-0058"},
        "existing_0640": {"WS-0059", "WS-0060"},
        "unreadable_source": {"WS-0061", "WS-0062"},
    }

    stale_label_workspaces = {
        operation_workspace[operation_id]
        for operation_id, row in receipts.items()
        if row["worker_release_label"] != workspace_release[operation_workspace[operation_id]]
    }
    assert stale_label_workspaces == {"WS-0002", "WS-0018", "WS-0035", "WS-0044", "WS-0053", "WS-0060"}
    connection.close()

    return {
        "allocation": dict(sorted(allocation.items())),
        "attempts": 180,
        "operations": 174,
        "retries": 6,
        "derived": {key: sorted(derived[key]) for key in EXPECTED},
        "affected": sorted(affected),
        "exposed_unaffected": sorted(exposed_unaffected),
        "safe_candidate": sorted(safe_candidate),
        "canaries": {key: sorted(value) for key, value in canary_sets.items()},
        "tags": tags,
        "artifact_sha256": {
            "incident.db": sha256(root / "incident.db"),
            "python-dotenv-upstream.bundle": sha256(root / "bundles" / "python-dotenv-upstream.bundle"),
            "dotenv-replacement-internal.bundle": sha256(root / "bundles" / "dotenv-replacement-internal.bundle"),
        },
    }


def write_ground_truth(path: Path, truth: dict[str, object]) -> None:
    derived = truth["derived"]
    assert isinstance(derived, dict)
    lines = [
        "# Author-only fixture ground truth",
        "",
        "This file is produced by the independent validator and is never copied into the runtime image.",
        "",
        "## Counts",
        "",
        "- Workspaces: 64",
        "- Potentially exposed: 52",
        "- Logical operations: 174",
        "- Attempts: 180",
        "- Retries: 6",
        "- Affected: 20",
        "- Exposed but unaffected: 32",
        "- Candidate workspaces: 12",
        "",
        "## Derived impact sets",
        "",
    ]
    for key in EXPECTED:
        values = set(derived[key])
        lines.append(f"- {key}: {format_ids(values)}")
    lines.extend(["", "## Machine-readable read-back", "", "```json", json.dumps(truth, indent=2, sort_keys=True), "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--ground-truth", type=Path)
    args = parser.parse_args()
    root = args.fixture_root.resolve()
    truth = validate(root)
    if args.ground_truth:
        write_ground_truth(args.ground_truth.resolve(), truth)
    print(json.dumps(truth, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
