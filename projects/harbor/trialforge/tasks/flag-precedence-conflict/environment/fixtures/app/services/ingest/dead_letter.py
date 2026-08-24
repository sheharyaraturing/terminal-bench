"""Dead-letter handling."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
MAX_REPLAY = 2000


def replay(queue, sink):
    if not flags.get_bool("ingest.dead_letter_replay", default=False):
        LOG.info("dead-letter replay disabled")
        return 0
    replayed = 0
    for message in queue.drain(limit=MAX_REPLAY):
        replayed += sink.accept(message)
    return replayed
