"""Shared string constants.

Some gates are referenced through a constant rather than inline, so the literal
appears here and not at the call site.
"""

FLAG_ASYNC_EXPORT = "reporting.background_export"

EXPORT_MIME = "application/x-ndjson"
MAX_EXPORT_PARTS = 64
RETRY_BACKOFF_MS = (100, 400, 1600, 6400)
