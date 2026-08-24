"""Report exports."""
import logging

from platform import flags
from platform.constants import EXPORT_MIME, FLAG_ASYNC_EXPORT, MAX_EXPORT_PARTS

LOG = logging.getLogger(__name__)


def export(report, sink):
    if flags.enabled(FLAG_ASYNC_EXPORT):
        return _enqueue(report, sink)
    return _stream(report, sink)


def _enqueue(report, sink):
    parts = min(report.estimated_parts, MAX_EXPORT_PARTS)
    return sink.enqueue(report.id, parts=parts, mime=EXPORT_MIME)


def _stream(report, sink):
    return sink.write(report.rows(), mime=EXPORT_MIME)
