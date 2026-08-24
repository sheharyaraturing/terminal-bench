"""Index writer."""
import logging

LOG = logging.getLogger(__name__)
BULK_SIZE = 500


def index_all(documents, client):
    written = 0
    for start in range(0, len(documents), BULK_SIZE):
        chunk = documents[start:start + BULK_SIZE]
        written += client.bulk([_action(doc) for doc in chunk])
    return written


def _action(doc):
    return {"index": {"_id": doc.id}, "doc": doc.body}
