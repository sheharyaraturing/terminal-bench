from datetime import datetime, timedelta, timezone


ASSESSMENT_INSTANT = datetime(2026, 4, 1, tzinfo=timezone.utc)


def creation_in_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def past_window(created_at: str, window_days: int) -> bool:
    cutoff = ASSESSMENT_INSTANT - timedelta(days=window_days)
    return creation_in_utc(created_at) < cutoff


def select_candidates(records, windows, active_hold_ids):
    return [
        record["record_id"]
        for record in records
        if record["record_id"] not in active_hold_ids
        and past_window(record["created_at"], windows[record["record_class"]])
    ]
