#!/usr/bin/env python3
"""Read SQL, logs, and Git back independently and emit authoring ground truth."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import subprocess
import tempfile
import tomllib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "bundles" / "retention-platform.bundle"
SQL = ROOT / "retention.sql"
LOG_ROOT = ROOT / "logs"
UPSTREAM_SHA = "debde74347f4147d0d2c745b1e4d98c1c64dfa74"
UPSTREAM_REF = "upstream-qumulo-filelock-debde743"
UPSTREAM_FILELOCK_SHA256 = "92c46ee2d28537b0a338a1522784e1c75887997e6cbec03c43c3f3f04d5b1c29"
UPSTREAM_LICENSE_SHA256 = "8310c9ba888d7e5b4a22980b22275841463f089f83ffc51e532409bed0351528"
SNAPSHOT = datetime(2026, 4, 1, tzinfo=timezone.utc)
DEPLOYMENT_ID = "DPL-20260401-017"
EVIDENCE_SOURCE_ID = "EVSRC-RETENTION-PLATFORM"
EVIDENCE_SOURCE_TYPE = "version_control_repository"
EVIDENCE_REPOSITORY_PATH = "/opt/retention-platform"
EXPECTED_HOLD_EVENTS = 67
EXPECTED_RECEIPT_EVENTS = 157
CLASS_ORDER = (
    "txn_log",
    "support_corr",
    "marketing_contact",
    "audit_trail",
    "hr_applicant",
    "session_replay",
)


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_windows(policy: str) -> dict[str, int]:
    entries = re.findall(
        r"### (3\.\d+) (.+?) — `([a-z_]+)`\n(.*?)(?=\n### |\n## )",
        policy,
        re.S,
    )
    sections: dict[str, str] = {}
    windows: dict[str, int] = {}
    unresolved: list[tuple[str, str]] = []
    for section, _label, code, body in entries:
        sections[section] = code
        match = re.search(r"Retention:\s*\*\*([\d,]+) days\*\*", body)
        if match:
            windows[code] = int(match.group(1).replace(",", ""))
        else:
            unresolved.append((code, body))
    for code, body in unresolved:
        section = re.search(r"assessed under §(3\.\d+)", body).group(1)
        windows[code] = windows[sections[section]]
    return windows


def ids(values: set[str] | list[str]) -> str:
    return ", ".join(f"`{value}`" for value in sorted(values))


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SQL.read_text(encoding="utf-8"))

    records = conn.execute(
        "SELECT record_id, record_class, created_at FROM retention_records "
        "ORDER BY record_id"
    ).fetchall()
    events = conn.execute(
        "SELECT event_id, record_id, event_type, effective_at, case_reference "
        "FROM retention_hold_events ORDER BY effective_at, event_id"
    ).fetchall()
    candidate_ids = {
        row[0]
        for row in conn.execute(
            "SELECT record_id FROM purge_candidates WHERE run_id = ?",
            ("PURGE-2026-04-01-A",),
        )
    }
    receipt_event_count = conn.execute(
        "SELECT COUNT(*) FROM purge_receipts WHERE run_id = ?",
        ("PURGE-2026-04-01-A",),
    ).fetchone()[0]
    receipt_ids = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT i.record_id FROM purge_receipts i "
            "WHERE i.run_id = ? AND i.event_type = 'receipt_issued' "
            "AND NOT EXISTS (SELECT 1 FROM purge_receipts v "
            "WHERE v.run_id = i.run_id AND v.receipt_id = i.receipt_id "
            "AND v.event_type = 'receipt_voided' AND v.event_at > i.event_at)",
            ("PURGE-2026-04-01-A",),
        )
    }
    retry_event_ids = {
        row[0]
        for row in conn.execute(
            "SELECT record_id FROM purge_receipts "
            "WHERE run_id = ? AND event_type = 'attempt_failed'",
            ("PURGE-2026-04-01-A",),
        )
    }
    replay_event_count = conn.execute(
        "SELECT COUNT(*) FROM purge_receipts "
        "WHERE run_id = ? AND event_type = 'receipt_replayed'",
        ("PURGE-2026-04-01-A",),
    ).fetchone()[0]
    voided_receipt_count = conn.execute(
        "SELECT COUNT(*) FROM purge_receipts "
        "WHERE run_id = ? AND event_type = 'receipt_voided'",
        ("PURGE-2026-04-01-A",),
    ).fetchone()[0]
    run_row = conn.execute(
        "SELECT * FROM purge_runs WHERE run_id = ?", ("PURGE-2026-04-01-A",)
    ).fetchone()
    evidence_rows = conn.execute(
        "SELECT s.source_id, s.source_type, s.repository_path "
        "FROM purge_runs r JOIN purge_evidence_sources s "
        "ON s.source_id = r.evidence_source_id WHERE r.run_id = ?",
        ("PURGE-2026-04-01-A",),
    ).fetchall()

    with tempfile.TemporaryDirectory(prefix="tf007-readback-") as tmp:
        repo = Path(tmp) / "repo"
        run("git", "clone", "-q", str(BUNDLE), str(repo))
        run("git", "checkout", "-q", "audit-review", cwd=repo)
        policy = (repo / "policies" / "RS-2026.1.md").read_text(encoding="utf-8")
        regulator_return = (
            repo / "reports" / "2026-Q1-regulator-return.md"
        ).read_text(encoding="utf-8")
        retention_readme = (repo / "RETENTION_PLATFORM.md").read_text(
            encoding="utf-8"
        )
        deploy = tomllib.loads(
            (repo / "deploy" / "production.toml").read_text(encoding="utf-8")
        )
        windows = parse_windows(policy)
        tags = set(run("git", "tag", cwd=repo).splitlines())
        production_sha = run(
            "git", "rev-parse", "refs/remotes/origin/production", cwd=repo
        )
        production_tag_sha = run("git", "rev-parse", "prod-2026-04-01", cwd=repo)
        review_sha = run("git", "rev-parse", "audit-review", cwd=repo)
        run("git", "cat-file", "-e", f"{UPSTREAM_REF}^{{commit}}", cwd=repo)
        run(
            "git",
            "merge-base",
            "--is-ancestor",
            UPSTREAM_REF,
            "refs/remotes/origin/production",
            cwd=repo,
        )
        upstream_filelock = run(
            "git", "show", f"{UPSTREAM_REF}:qfs_filelock.py", cwd=repo
        )
        upstream_provenance = run(
            "git", "show", f"{UPSTREAM_REF}:UPSTREAM_PROVENANCE.md", cwd=repo
        )
        upstream_filelock_sha = digest(repo / "qfs_filelock.py")
        upstream_license_sha = digest(repo / "LICENSE")
        selector_old = run(
            "git",
            "show",
            "selector-v2.3.1:platform_retention/selector.py",
            cwd=repo,
        )
        selector_deployed = run(
            "git",
            "show",
            "selector-v2.4.0:platform_retention/selector.py",
            cwd=repo,
        )
        hold_deployed = run(
            "git",
            "show",
            "lock-adapter-v1.8.1:platform_retention/hold_adapter.py",
            cwd=repo,
        )
        hold_fixed = run(
            "git",
            "show",
            "lock-adapter-v1.8.2:platform_retention/hold_adapter.py",
            cwd=repo,
        )
        assert not (repo / "qfs_filelock_config.ini").exists()
        assert not (repo / "test_qfs_filelock.sh").exists()
        assert (repo / "LICENSE").is_file()
        internal_log = run(
            "git", "log", "--reverse", "--format=%h %ad %s", "--date=short",
            f"{UPSTREAM_REF}..audit-review", cwd=repo
        ).splitlines()

    required_tags = {
        "selector-v2.3.1",
        "selector-v2.4.0",
        "lock-adapter-v1.8.1",
        "lock-adapter-v1.8.2",
        "RS-2026.1",
        "prod-2026-04-01",
        UPSTREAM_REF,
    }
    assert required_tags.issubset(tags)
    assert production_sha == production_tag_sha
    assert review_sha != production_sha
    assert "171 records past" in regulator_return
    assert "151 records eligible" in regulator_return
    assert "two inventory records" in regulator_return
    assert ".astimezone(timezone.utc)" in selector_old
    assert "value[:19]" in selector_deployed
    assert "recent_locks = {}" in upstream_filelock
    assert "current_time - recent_locks[full_path]" in upstream_filelock
    assert "< cooldown" in upstream_filelock
    assert UPSTREAM_SHA in upstream_provenance
    assert UPSTREAM_FILELOCK_SHA256 in upstream_provenance
    assert UPSTREAM_LICENSE_SHA256 in upstream_provenance
    assert upstream_filelock_sha == UPSTREAM_FILELOCK_SHA256
    assert upstream_license_sha == UPSTREAM_LICENSE_SHA256
    assert "return storage_path in recent_locks" in hold_deployed
    assert "del now_epoch, cooldown_seconds" in hold_deployed
    assert "now_epoch - cached_at < cooldown_seconds" in hold_fixed
    assert "five-second" not in retention_readme
    assert "debounce" not in retention_readme
    assert deploy["deployment_id"] == DEPLOYMENT_ID
    assert deploy["policy_release"] == "RS-2026.1"
    assert deploy["selector_release"] == "selector-v2.4.0"
    assert deploy["lock_adapter_release"] == "lock-adapter-v1.8.1"
    assert deploy["storage_lock_contract_ref"] == UPSTREAM_REF

    latest_event: dict[str, sqlite3.Row] = {}
    placed_ever: set[str] = set()
    for event in events:
        effective = datetime.fromisoformat(event["effective_at"].replace("Z", "+00:00"))
        if effective <= SNAPSHOT:
            latest_event[event["record_id"]] = event
            if event["event_type"] == "placed":
                placed_ever.add(event["record_id"])
    active_holds = {
        record_id
        for record_id, event in latest_event.items()
        if event["event_type"] == "placed"
    }
    released_holds = {
        record_id
        for record_id, event in latest_event.items()
        if event["event_type"] == "released"
    }
    released_ever = {
        event["record_id"]
        for event in events
        if event["event_type"] == "released"
        and datetime.fromisoformat(event["effective_at"].replace("Z", "+00:00"))
        <= SNAPSHOT
    }
    any_release_active = placed_ever.difference(released_ever)

    cutoffs = {
        record_class: SNAPSHOT - timedelta(days=days)
        for record_class, days in windows.items()
    }
    by_class: dict[str, list[sqlite3.Row]] = defaultdict(list)
    utc_created: dict[str, datetime] = {}
    wall_created: dict[str, datetime] = {}
    for record in records:
        by_class[record["record_class"]].append(record)
        utc_created[record["record_id"]] = datetime.fromisoformat(
            record["created_at"]
        ).astimezone(timezone.utc)
        wall_created[record["record_id"]] = datetime.fromisoformat(
            record["created_at"][:19]
        ).replace(tzinfo=timezone.utc)

    past_ids = {
        record["record_id"]
        for record in records
        if utc_created[record["record_id"]] < cutoffs[record["record_class"]]
    }
    eligible_ids = past_ids.difference(active_holds)
    naive_past_ids = {
        record["record_id"]
        for record in records
        if wall_created[record["record_id"]] < cutoffs[record["record_class"]]
    }
    positive_offset_eligible = past_ids.difference(naive_past_ids)
    negative_offset_inside = naive_past_ids.difference(past_ids)
    boundary_ids = {
        record["record_id"]
        for record in records
        if utc_created[record["record_id"]] == cutoffs[record["record_class"]]
    }
    overdue_holds = past_ids.intersection(active_holds)
    skips = candidate_ids.difference(receipt_ids)
    wrongful_deletions = receipt_ids.difference(eligible_ids)
    eligible_misses = eligible_ids.difference(receipt_ids)
    stale_hold_misses = eligible_misses.intersection(released_holds)

    log_paths = sorted(LOG_ROOT.glob("purge-worker-*.log"))
    log_text = "\n".join(path.read_text(encoding="utf-8") for path in log_paths)
    log_skips = set(
        re.findall(
            r"record_id=(REC-\d+) attempt=1 result=skipped code=object_locked",
            log_text,
        )
    )
    transient_failures = set(
        re.findall(
            r"record_id=(REC-\d+) attempt=1 result=failed code=storage_timeout",
            log_text,
        )
    )
    recent_lock_cache_ages = {}
    for observed_at, record_id, cached_at in re.findall(
        r"(\S+) WARN run_id=\S+ record_id=(REC-\d+).*?"
        r"result=skipped code=object_locked .*?cached_at=(\S+)",
        log_text,
    ):
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        cached = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        recent_lock_cache_ages[record_id] = int((observed - cached).total_seconds())
    retry_successes = {
        record_id
        for record_id in transient_failures
        if re.search(
            rf"record_id={record_id} attempt=2 result=deleted receipt_id=",
            log_text,
        )
    }
    worker_headers = re.findall(r"event=worker_started", log_text)
    deployment_headers = re.findall(
        rf"deployment_id={DEPLOYMENT_ID}", log_text
    )

    per_class: dict[str, tuple[int, int, int, int]] = {}
    for record_class in CLASS_ORDER:
        inventory = len(by_class[record_class])
        past = len(
            {
                record["record_id"] for record in by_class[record_class]
            }.intersection(past_ids)
        )
        held = len(
            {
                record["record_id"] for record in by_class[record_class]
            }.intersection(overdue_holds)
        )
        per_class[record_class] = (inventory, past, held, past - held)

    assert len(records) == 400
    assert len(events) == EXPECTED_HOLD_EVENTS
    assert len(active_holds) == 36
    assert len(active_holds.difference(any_release_active)) == 4
    assert len(overdue_holds) == 20
    assert len(past_ids) == 169
    assert len(eligible_ids) == 149
    assert len(candidate_ids) == 153
    assert receipt_event_count == EXPECTED_RECEIPT_EVENTS
    assert len(receipt_ids) == 146
    assert replay_event_count == 3
    assert voided_receipt_count == 2
    assert len(log_paths) == len(worker_headers) == 6
    assert skips == log_skips and len(skips) == 7
    assert set(recent_lock_cache_ages) == skips
    assert all(age > 5 for age in recent_lock_cache_ages.values())
    assert transient_failures == retry_successes and len(transient_failures) == 4
    assert retry_event_ids == transient_failures
    assert len(positive_offset_eligible) == 5
    assert len(negative_offset_inside) == 9
    assert len(boundary_ids) == 2
    assert wrongful_deletions == negative_offset_inside
    assert len(wrongful_deletions) == 9
    assert len(eligible_misses) == 12
    assert stale_hold_misses == skips
    assert len(wrongful_deletions | eligible_misses) == 21
    assert run_row["deployment_id"] == deploy["deployment_id"]
    assert run_row["evidence_source_id"] == EVIDENCE_SOURCE_ID
    assert len(evidence_rows) == 1
    assert evidence_rows[0]["source_id"] == EVIDENCE_SOURCE_ID
    assert evidence_rows[0]["source_type"] == EVIDENCE_SOURCE_TYPE
    assert evidence_rows[0]["repository_path"] == EVIDENCE_REPOSITORY_PATH
    assert len(deployment_headers) == 6
    assert not re.search(
        r"selector-v|lock-adapter|RS-2026|qfs_recent|cache_age_seconds|evidence_repo",
        log_text,
    )

    output: list[str] = []
    write = output.append
    write("# Ground truth — retention-purge-gap v6")
    write("")
    write("Generated by `verify_fixture.py` after independently reopening the SQLite fixture, all six worker logs and the completed Git bundle. This file is authoring evidence only and is not copied into the runtime environment.")
    write("")
    write("## Fixture integrity")
    write("")
    write(f"- SQL SHA-256: `{digest(SQL)}`")
    write(f"- internal bundle SHA-256: `{digest(BUNDLE)}`")
    write(f"- pinned upstream source: Qumulo/filelock `{UPSTREAM_SHA}` imported at tag `{UPSTREAM_REF}` with verified source and license hashes")
    write(f"- production commit/tag: `{production_sha}`")
    write(f"- audit-review head: `{review_sha}`")
    write(f"- rows: {len(records)} records, {len(events)} hold events, {len(candidate_ids)} candidates, {receipt_event_count} receipt events and {len(receipt_ids)} unique final receipts")
    write(f"- deployment evidence locator: `{run_row['deployment_id']}` resolves through `{evidence_rows[0]['source_id']}` (`{evidence_rows[0]['source_type']}`) to `{evidence_rows[0]['repository_path']}`")
    write("")
    write("Internal commits read from the bundle:")
    write("")
    for line in internal_log:
        write(f"- `{line}`")
    write("")
    write("## Compliance reconciliation")
    write("")
    write("| category | inventory | past window | active exception | eligible |")
    write("|---|---:|---:|---:|---:|")
    for record_class in CLASS_ORDER:
        inventory, past, held, eligible = per_class[record_class]
        write(f"| `{record_class}` | {inventory} | **{past}** | {held} | **{eligible}** |")
    write("| **total** | **400** | **169** | **20** | **149** |")
    write("")
    write(f"The 20 past-window records withheld by an active legal hold are: {ids(overdue_holds)}.")
    write("")
    write(f"The five positive-offset records that remain eligible are: {ids(positive_offset_eligible)}.")
    write("")
    write(f"The nine negative-offset records that remain inside-window are: {ids(negative_offset_inside)}.")
    write("")
    write(f"The exact-boundary records, excluded by the strict-exceeds rule, are: {ids(boundary_ids)}.")
    write("")
    write("The rejected Q1 submission reported 171 past-window and 151 eligible records. Its regulator return says that two UTC-normalised records landed exactly on their cut-offs and must be identified and removed. Those records are the two exact-boundary IDs above; the corrected totals are 169 and 149.")
    write("")
    write("## Latest purge")
    write("")
    write(f"- `{run_row['run_id']}` selected **{len(candidate_ids)}** candidates, logged **{len(skips)}** object-lock skips and produced **{len(receipt_ids)}** unique final deletion receipts from **{receipt_event_count}** append-only receipt events.")
    write(f"- released-hold skips: {ids(skips)}")
    write(f"- transient storage failures that later succeeded: {ids(transient_failures)}")
    write(f"- journal noise: {replay_event_count} replay events and {voided_receipt_count} voided provisional receipts; neither changes the final deletion set")
    write(f"- deployment `{deploy['deployment_id']}` resolves in Git to `{deploy['policy_release']}`, `{deploy['selector_release']}` and `{deploy['lock_adapter_release']}`")
    write("")
    write("## Root causes and exposure")
    write("")
    write("- `selector-v2.3.1` normalises the supplied timestamp with `astimezone(timezone.utc)`; deployed `selector-v2.4.0` instead parses only `value[:19]` and assigns UTC. The resulting purge set contains the nine negative-offset records and misses the five positive-offset records listed above.")
    write("- pinned Qumulo/filelock uses `recent_locks` only as a five-second path debounce and checks each entry's age. Deployed `lock-adapter-v1.8.1` instead treats membership in the restored cache as durable object-lock state and ignores age; `lock-adapter-v1.8.2` restores the upstream expiry check. Seven cache entries were far older than five seconds even though the corresponding holds had been released, producing the seven skips listed above.")
    write(f"- wrongful deletions: **{len(wrongful_deletions)}** — {ids(wrongful_deletions)}")
    write(f"- eligible misses: **{len(eligible_misses)}** — {ids(eligible_misses)}")
    write(f"- divergent treatments: **{len(wrongful_deletions | eligible_misses)}**")
    print("\n".join(output).rstrip())


if __name__ == "__main__":
    main()
