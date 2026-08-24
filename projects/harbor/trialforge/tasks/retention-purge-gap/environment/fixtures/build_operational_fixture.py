#!/usr/bin/env python3
"""Build deterministic SQLite and worker-log evidence from the base fixtures."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SNAPSHOT = datetime(2026, 4, 1, tzinfo=timezone.utc)
RUN_ID = "PURGE-2026-04-01-A"
DEPLOYMENT_ID = "DPL-20260401-017"
EVIDENCE_SOURCE_ID = "EVSRC-RETENTION-PLATFORM"
EVIDENCE_SOURCE_TYPE = "version_control_repository"
EVIDENCE_REPOSITORY_PATH = "/opt/retention-platform"
SKIP_IDS = (
    "REC-00005",
    "REC-00012",
    "REC-00013",
    "REC-00028",
    "REC-00040",
    "REC-00046",
    "REC-00108",
)
RETRY_IDS = ("REC-00019", "REC-00027", "REC-00063", "REC-00064")
REPLAY_IDS = ("REC-00039", "REC-00043", "REC-00053")
VOID_REISSUE_IDS = ("REC-00061", "REC-00066")
MULTI_CYCLE_ACTIVE_IDS = (
    "REC-00004",
    "REC-00017",
    "REC-00041",
    "REC-00065",
)
MULTI_CYCLE_RELEASED_IDS = ("REC-00005", "REC-00012")
POST_SNAPSHOT_RELEASES = 5
EXPECTED_HOLD_EVENTS = 67
EXPECTED_RECEIPT_EVENTS = 157


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_windows(policy: str) -> dict[str, int]:
    entries = re.findall(
        r"### (3\.\d+) (.+?) — `([a-z_]+)`\n(.*?)(?=\n### |\n## )",
        policy,
        re.S,
    )
    stated: dict[str, int] = {}
    sections: dict[str, str] = {}
    unresolved: list[tuple[str, str]] = []
    for section, _name, code, body in entries:
        sections[section] = code
        match = re.search(r"Retention:\s*\*\*([\d,]+) days\*\*", body)
        if match:
            stated[code] = int(match.group(1).replace(",", ""))
        else:
            unresolved.append((code, body))
    for code, body in unresolved:
        section = re.search(r"assessed under §(3\.\d+)", body).group(1)
        stated[code] = stated[sections[section]]
    return stated


def build_hold_events(records: list[dict[str, str]]) -> list[dict[str, str]]:
    by_id = {row["record_id"]: row for row in records}
    active_ids = sorted(
        row["record_id"] for row in records if row["legal_hold"] == "true"
    )
    assert len(active_ids) == 36
    assert not set(active_ids).intersection(SKIP_IDS)

    raw_events: list[dict[str, object]] = []
    for index, record_id in enumerate(active_ids, start=1):
        created = datetime.fromisoformat(by_id[record_id]["created_at"]).astimezone(
            timezone.utc
        )
        placed = max(
            created + timedelta(days=1),
            datetime(2025, 1, 2, tzinfo=timezone.utc) + timedelta(days=index),
        )
        if record_id in MULTI_CYCLE_ACTIVE_IDS:
            prior_placed = max(
                created + timedelta(days=1),
                datetime(2024, 6, 1, tzinfo=timezone.utc)
                + timedelta(days=index),
            )
            prior_released = prior_placed + timedelta(days=21)
            placed = max(placed, prior_released + timedelta(days=21))
            raw_events.extend(
                (
                    {
                        "record_id": record_id,
                        "event_type": "placed",
                        "effective_at": prior_placed,
                        "case_reference": f"LH-HIST-{index:03d}",
                    },
                    {
                        "record_id": record_id,
                        "event_type": "released",
                        "effective_at": prior_released,
                        "case_reference": f"LH-HIST-{index:03d}",
                    },
                )
            )
        if placed >= SNAPSHOT:
            placed = SNAPSHOT - timedelta(days=1, minutes=index)
        case = f"LH-ACT-{index:03d}"
        raw_events.append(
            {
                "record_id": record_id,
                "event_type": "placed",
                "effective_at": placed,
                "case_reference": case,
            }
        )
        if index <= POST_SNAPSHOT_RELEASES:
            raw_events.append(
                {
                    "record_id": record_id,
                    "event_type": "released",
                    "effective_at": SNAPSHOT + timedelta(days=1, hours=index),
                    "case_reference": case,
                }
            )

    for index, record_id in enumerate(SKIP_IDS, start=1):
        created = datetime.fromisoformat(by_id[record_id]["created_at"]).astimezone(
            timezone.utc
        )
        placed = max(
            created + timedelta(days=1),
            datetime(2025, 2, 1, tzinfo=timezone.utc) + timedelta(days=index),
        )
        if record_id in MULTI_CYCLE_RELEASED_IDS:
            prior_placed = max(
                created + timedelta(days=1),
                datetime(2024, 5, 1, tzinfo=timezone.utc)
                + timedelta(days=index),
            )
            prior_released = prior_placed + timedelta(days=21)
            placed = max(placed, prior_released + timedelta(days=90))
            raw_events.extend(
                (
                    {
                        "record_id": record_id,
                        "event_type": "placed",
                        "effective_at": prior_placed,
                        "case_reference": f"LH-HIST-REL-{index:03d}",
                    },
                    {
                        "record_id": record_id,
                        "event_type": "released",
                        "effective_at": prior_released,
                        "case_reference": f"LH-HIST-REL-{index:03d}",
                    },
                )
            )
        released = placed + timedelta(days=30)
        assert released < SNAPSHOT
        case = f"LH-REL-{index:03d}"
        raw_events.extend(
            (
                {
                    "record_id": record_id,
                    "event_type": "placed",
                    "effective_at": placed,
                    "case_reference": case,
                },
                {
                    "record_id": record_id,
                    "event_type": "released",
                    "effective_at": released,
                    "case_reference": case,
                },
            )
        )

    raw_events.sort(
        key=lambda event: (
            event["effective_at"],
            event["record_id"],
            event["event_type"],
        )
    )
    events: list[dict[str, str]] = []
    for index, event in enumerate(raw_events, start=1):
        events.append(
            {
                "event_id": f"HOLD-EVT-{index:03d}",
                "record_id": str(event["record_id"]),
                "event_type": str(event["event_type"]),
                "effective_at": iso(event["effective_at"]),
                "case_reference": str(event["case_reference"]),
            }
        )
    assert len(events) == EXPECTED_HOLD_EVENTS
    return events


def active_holds_at(
    events: list[dict[str, str]], instant: datetime
) -> set[str]:
    latest: dict[str, dict[str, str]] = {}
    for event in sorted(events, key=lambda item: item["effective_at"]):
        if datetime.fromisoformat(event["effective_at"].replace("Z", "+00:00")) <= instant:
            latest[event["record_id"]] = event
    return {
        record_id
        for record_id, event in latest.items()
        if event["event_type"] == "placed"
    }


def build_sql(
    records: list[dict[str, str]],
    events: list[dict[str, str]],
    candidates: list[str],
    receipt_events: list[dict[str, str | int | None]],
) -> str:
    lines = [
        "PRAGMA foreign_keys = ON;",
        "BEGIN;",
        "CREATE TABLE retention_records (",
        "  record_id TEXT PRIMARY KEY,",
        "  record_class TEXT NOT NULL,",
        "  created_at TEXT NOT NULL",
        ");",
        "CREATE TABLE retention_hold_events (",
        "  event_id TEXT PRIMARY KEY,",
        "  record_id TEXT NOT NULL REFERENCES retention_records(record_id),",
        "  event_type TEXT NOT NULL CHECK (event_type IN ('placed', 'released')),",
        "  effective_at TEXT NOT NULL,",
        "  case_reference TEXT NOT NULL",
        ");",
        "CREATE INDEX idx_retention_hold_record_time",
        "  ON retention_hold_events(record_id, effective_at);",
        "CREATE TABLE purge_evidence_sources (",
        "  source_id TEXT PRIMARY KEY,",
        "  source_type TEXT NOT NULL,",
        "  repository_path TEXT NOT NULL",
        ");",
        "CREATE TABLE purge_runs (",
        "  run_id TEXT PRIMARY KEY,",
        "  assessment_instant TEXT NOT NULL,",
        "  started_at TEXT NOT NULL,",
        "  completed_at TEXT NOT NULL,",
        "  deployment_id TEXT NOT NULL,",
        "  evidence_source_id TEXT NOT NULL REFERENCES purge_evidence_sources(source_id),",
        "  status TEXT NOT NULL",
        ");",
        "CREATE TABLE purge_candidates (",
        "  run_id TEXT NOT NULL REFERENCES purge_runs(run_id),",
        "  sequence_no INTEGER NOT NULL,",
        "  record_id TEXT NOT NULL REFERENCES retention_records(record_id),",
        "  selected_at TEXT NOT NULL,",
        "  PRIMARY KEY (run_id, record_id),",
        "  UNIQUE (run_id, sequence_no)",
        ");",
        "CREATE TABLE purge_receipts (",
        "  event_id TEXT PRIMARY KEY,",
        "  run_id TEXT NOT NULL REFERENCES purge_runs(run_id),",
        "  record_id TEXT NOT NULL REFERENCES retention_records(record_id),",
        "  receipt_id TEXT,",
        "  attempt_no INTEGER NOT NULL,",
        "  event_type TEXT NOT NULL CHECK (event_type IN ('attempt_failed', 'receipt_issued', 'receipt_voided', 'receipt_replayed')),",
        "  event_at TEXT NOT NULL,",
        "  storage_key TEXT NOT NULL,",
        "  detail TEXT NOT NULL",
        ");",
        "CREATE INDEX idx_purge_receipt_record_time",
        "  ON purge_receipts(run_id, record_id, event_at);",
        "CREATE INDEX idx_purge_receipt_id_time",
        "  ON purge_receipts(receipt_id, event_at);",
    ]
    for row in sorted(records, key=lambda item: item["record_id"]):
        lines.append(
            "INSERT INTO retention_records VALUES "
            f"({sql_text(row['record_id'])}, {sql_text(row['class'])}, "
            f"{sql_text(row['created_at'])});"
        )
    for event in events:
        lines.append(
            "INSERT INTO retention_hold_events VALUES "
            f"({sql_text(event['event_id'])}, {sql_text(event['record_id'])}, "
            f"{sql_text(event['event_type'])}, {sql_text(event['effective_at'])}, "
            f"{sql_text(event['case_reference'])});"
        )
    lines.append(
        "INSERT INTO purge_evidence_sources VALUES "
        f"({sql_text(EVIDENCE_SOURCE_ID)}, {sql_text(EVIDENCE_SOURCE_TYPE)}, "
        f"{sql_text(EVIDENCE_REPOSITORY_PATH)});"
    )
    lines.append(
        "INSERT INTO purge_runs VALUES "
        f"({sql_text(RUN_ID)}, '2026-04-01T00:00:00Z', "
        f"'2026-04-01T01:00:00Z', '2026-04-01T01:18:42Z', "
        f"{sql_text(DEPLOYMENT_ID)}, {sql_text(EVIDENCE_SOURCE_ID)}, "
        "'completed_with_skips');"
    )
    for index, record_id in enumerate(candidates, start=1):
        selected_at = datetime(2026, 4, 1, 0, 45, tzinfo=timezone.utc) + timedelta(
            milliseconds=index
        )
        lines.append(
            "INSERT INTO purge_candidates VALUES "
            f"({sql_text(RUN_ID)}, {index}, {sql_text(record_id)}, "
            f"{sql_text(selected_at.isoformat(timespec='milliseconds').replace('+00:00', 'Z'))});"
        )
    for event in receipt_events:
        receipt_id = (
            "NULL"
            if event["receipt_id"] is None
            else sql_text(str(event["receipt_id"]))
        )
        lines.append(
            "INSERT INTO purge_receipts VALUES "
            f"({sql_text(str(event['event_id']))}, {sql_text(RUN_ID)}, "
            f"{sql_text(str(event['record_id']))}, {receipt_id}, "
            f"{event['attempt_no']}, {sql_text(str(event['event_type']))}, "
            f"{sql_text(str(event['event_at']))}, "
            f"{sql_text(str(event['storage_key']))}, "
            f"{sql_text(str(event['detail']))});"
        )
    lines.extend(("COMMIT;", ""))
    return "\n".join(lines)


def build_receipt_events(receipts: list[str]) -> list[dict[str, str | int | None]]:
    events: list[dict[str, str | int | None]] = []

    def append_event(
        record_id: str,
        receipt_id: str | None,
        attempt_no: int,
        event_type: str,
        event_at: datetime,
        detail: str,
    ) -> None:
        events.append(
            {
                "event_id": f"RCPT-EVT-{len(events) + 1:04d}",
                "record_id": record_id,
                "receipt_id": receipt_id,
                "attempt_no": attempt_no,
                "event_type": event_type,
                "event_at": iso(event_at),
                "storage_key": f"objects/retention/{record_id}.json",
                "detail": detail,
            }
        )

    base = datetime(2026, 4, 1, 1, 2, tzinfo=timezone.utc)
    for index, record_id in enumerate(receipts, start=1):
        final_at = base + timedelta(seconds=index * 4)
        final_receipt = f"DEL-20260401-{index:04d}"
        final_attempt = 1
        if record_id in RETRY_IDS:
            append_event(
                record_id,
                None,
                1,
                "attempt_failed",
                final_at - timedelta(seconds=1),
                "storage_timeout",
            )
            final_attempt = 2
        elif record_id in VOID_REISSUE_IDS:
            provisional = f"DEL-PROV-20260401-{index:04d}"
            append_event(
                record_id,
                provisional,
                1,
                "receipt_issued",
                final_at - timedelta(seconds=2),
                "provisional_confirmation",
            )
            append_event(
                record_id,
                provisional,
                1,
                "receipt_voided",
                final_at - timedelta(seconds=1),
                "confirmation_timeout",
            )
            final_attempt = 2
        append_event(
            record_id,
            final_receipt,
            final_attempt,
            "receipt_issued",
            final_at,
            "deletion_confirmed",
        )
        if record_id in REPLAY_IDS:
            append_event(
                record_id,
                final_receipt,
                final_attempt,
                "receipt_replayed",
                final_at + timedelta(seconds=1),
                "journal_delivery_replay",
            )

    assert len(events) == EXPECTED_RECEIPT_EVENTS
    return events


def build_logs(
    candidates: list[str],
    receipts: set[str],
    recent_lock_times: dict[str, datetime],
) -> None:
    log_root = ROOT / "logs"
    log_root.mkdir(exist_ok=True)
    for stale in log_root.glob("purge-worker-*.log"):
        stale.unlink()

    workers: dict[int, list[str]] = defaultdict(list)
    for worker in range(1, 7):
        workers[worker].append(
            "2026-04-01T01:00:00Z INFO "
            f"run_id={RUN_ID} worker=purge-worker-{worker:02d} "
            f"deployment_id={DEPLOYMENT_ID} event=worker_started"
        )

    base = datetime(2026, 4, 1, 1, 2, tzinfo=timezone.utc)
    receipt_number = {
        record_id: index
        for index, record_id in enumerate(sorted(receipts), start=1)
    }
    for index, record_id in enumerate(candidates, start=1):
        worker = ((index - 1) % 6) + 1
        when = base + timedelta(seconds=index * 4)
        common = f"run_id={RUN_ID} record_id={record_id}"
        if record_id in SKIP_IDS:
            cached_at = recent_lock_times[record_id]
            workers[worker].append(
                f"{iso(when)} WARN {common} attempt=1 result=skipped "
                "code=object_locked "
                f"object_path=/objects/retention/{record_id}.json "
                f"cached_at={iso(cached_at)}"
            )
        elif record_id in RETRY_IDS:
            number = receipt_number[record_id]
            when = base + timedelta(seconds=number * 4)
            workers[worker].append(
                f"{iso(when - timedelta(seconds=1))} ERROR {common} attempt=1 "
                "result=failed code=storage_timeout"
            )
            workers[worker].append(
                f"{iso(when)} INFO {common} attempt=2 result=deleted "
                f"receipt_id=DEL-20260401-{number:04d}"
            )
        elif record_id in VOID_REISSUE_IDS:
            number = receipt_number[record_id]
            when = base + timedelta(seconds=number * 4)
            workers[worker].append(
                f"{iso(when - timedelta(seconds=1))} WARN {common} attempt=1 "
                "result=receipt_voided code=confirmation_timeout "
                f"receipt_id=DEL-PROV-20260401-{number:04d}"
            )
            workers[worker].append(
                f"{iso(when)} INFO {common} attempt=2 result=deleted "
                f"receipt_id=DEL-20260401-{number:04d}"
            )
        else:
            number = receipt_number[record_id]
            when = base + timedelta(seconds=number * 4)
            workers[worker].append(
                f"{iso(when)} INFO {common} attempt=1 result=deleted "
                f"receipt_id=DEL-20260401-{number:04d}"
            )
    for worker, lines in workers.items():
        lines = [lines[0], *sorted(lines[1:])]
        lines.append(
            "2026-04-01T01:18:42Z INFO "
            f"run_id={RUN_ID} worker=purge-worker-{worker:02d} event=worker_stopped"
        )
        (log_root / f"purge-worker-{worker:02d}.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


def main() -> None:
    policy = (ROOT / "policy.md").read_text(encoding="utf-8")
    windows = read_windows(policy)
    records = list(
        csv.DictReader((ROOT / "records.csv").open(encoding="utf-8", newline=""))
    )
    assert len(records) == 400
    events = build_hold_events(records)
    active = active_holds_at(events, SNAPSHOT)
    assert len(active) == 36

    cutoffs = {
        record_class: SNAPSHOT - timedelta(days=days)
        for record_class, days in windows.items()
    }
    correct_eligible: set[str] = set()
    candidates: list[str] = []
    for row in records:
        utc_created = datetime.fromisoformat(row["created_at"]).astimezone(timezone.utc)
        wall_clock_as_utc = datetime.fromisoformat(row["created_at"][:19]).replace(
            tzinfo=timezone.utc
        )
        if utc_created < cutoffs[row["class"]] and row["record_id"] not in active:
            correct_eligible.add(row["record_id"])
        if wall_clock_as_utc < cutoffs[row["class"]] and row["record_id"] not in active:
            candidates.append(row["record_id"])
    candidates.sort()
    receipts = sorted(set(candidates).difference(SKIP_IDS))
    receipt_events = build_receipt_events(receipts)

    assert len(correct_eligible) == 149
    assert len(candidates) == 153
    assert set(SKIP_IDS).issubset(candidates)
    assert set(RETRY_IDS).issubset(receipts)
    assert set(REPLAY_IDS).issubset(receipts)
    assert set(VOID_REISSUE_IDS).issubset(receipts)
    assert len(receipts) == 146
    assert len(set(receipts).difference(correct_eligible)) == 9
    assert len(correct_eligible.difference(receipts)) == 12

    (ROOT / "retention.sql").write_text(
        build_sql(records, events, candidates, receipt_events), encoding="utf-8"
    )
    recent_lock_times = {
        event["record_id"]: datetime.fromisoformat(
            event["effective_at"].replace("Z", "+00:00")
        )
        for event in events
        if event["record_id"] in SKIP_IDS and event["event_type"] == "placed"
    }
    assert set(recent_lock_times) == set(SKIP_IDS)
    build_logs(candidates, set(receipts), recent_lock_times)
    print(
        "wrote retention.sql and 6 logs: "
        f"records={len(records)} events={len(events)} candidates={len(candidates)} "
        f"receipt_events={len(receipt_events)} final_receipts={len(receipts)}"
    )


if __name__ == "__main__":
    main()
