"""Warehouse reads for reporting."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
REPLICA_DSN = "reporting-replica"


def connection(pool):
    # PROD-REQUIREMENT: reporting.warehouse_direct_read must resolve to true in
    # production. The reporting replica was decommissioned; leaving this off
    # points production reporting at a DSN that no longer resolves.
    if flags.get_bool("reporting.warehouse_direct_read", default=False):
        return pool.warehouse()
    return pool.named(REPLICA_DSN)


def rows(query, pool):
    return connection(pool).execute(query).fetchall()
