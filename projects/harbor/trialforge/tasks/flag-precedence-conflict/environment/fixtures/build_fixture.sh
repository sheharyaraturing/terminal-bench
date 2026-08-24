#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — flag-precedence-conflict
#
# Emits, into the directory this script lives in:
#   flags/default.json   the baseline layer  (21 keys)
#   flags/staging.json   the shared pre-production overlay
#   flags/prod.json      the production-only overlay
#   flags/README.md      the current resolution contract
#   flags/runtime-overrides.json
#   deploy/production-snapshot.json
#   deploy/effective-flag-report.json
#   app/**               the application tree, shipping manifest and alias map
#   docs/**              dated operational documentation
#   GROUND_TRUTH.*       author-only results from audit_fixture.py
#
# DETERMINISM: the flag layers, the flag-bearing source files and the README are
# all written from literal tables — no randomness touches them. The filler
# modules that give the tree its search volume are generated from
# random.Random(4471), consumed in one fixed pass over a sorted file list, so a
# re-run produces byte-identical output. Verify with:
#     find flags app deploy docs -type f | sort | xargs sha256sum | sha256sum
#
# Run:  bash build_fixture.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

rm -rf flags app deploy docs GROUND_TRUTH.json GROUND_TRUTH.md

python3 - <<'BUILD'
import json, os, random, textwrap

rng = random.Random(4471)

# ── THE FLAG LAYERS ──────────────────────────────────────────────────────────
# (flag, default, staging, prod)   None = the key is absent from that layer.
#
# Invariants this table is built to hold, all re-derived by the read-back stage:
#   * exactly ONE flag has a redundant override — an override whose value equals
#     the value it overrides. That is the decoy.
#   * exactly ONE flag is defined in a layer and referenced nowhere in app/.
#   * exactly ONE name is referenced in app/ and defined in no layer at all.
#   * four flags carry a PROD-REQUIREMENT comment; exactly one is violated.
LAYERS = [
    # flag                                   default  staging  prod
    ("checkout.express_lane",                False,   True,    None),
    ("checkout.retry_budget",                2,       5,       3),
    ("payments.dual_write_ledger",           False,   True,    None),   # L1 defect
    ("payments.settlement_batch_size",       200,     None,    500),
    ("payments.card_tokenization_v2",        True,    None,    None),
    ("billing.legacy_invoice_pdf",           False,   True,    False),  # L2 dead
    ("billing.proration_v3",                 False,   True,    None),
    ("notifications.digest_window_minutes",  30,      30,      30),     # decoy
    ("notifications.push_quiet_hours",       True,    False,   True),
    ("search.typo_tolerance",                True,    False,   None),
    ("reporting.async_export",               False,   True,    None),
    ("reporting.warehouse_direct_read",      False,   None,    True),
    ("platform.request_shadowing",           False,   True,    False),
    ("platform.circuit_breaker_ms",          1500,    800,     600),
    ("identity.mfa_grace_hours",             24,      None,    0),
    ("identity.session_pinning",             True,    False,   True),
    ("identity.passkey_enrolment",           False,   True,    None),
    ("ingest.max_batch_rows",                1000,    5000,    2000),
    ("ingest.dead_letter_replay",            False,   None,    True),
    ("web.new_nav",                          False,   True,    False),
    ("web.skeleton_loaders",                 True,    None,    None),
]
# search.semantic_rerank is deliberately in NO layer. It is referenced twice in
# app/ and therefore resolves to whatever each call site passes as a fallback —
# and the two call sites pass different fallbacks.

os.makedirs("flags", exist_ok=True)

def layer(idx):
    return {f: v for f, d, s, p in [(x[0], x[1], x[2], x[3]) for x in LAYERS]
            for v in [(d, s, p)[idx]] if v is not None}

for name, idx in (("default", 0), ("staging", 1), ("prod", 2)):
    with open(f"flags/{name}.json", "w", encoding="utf-8") as fh:
        json.dump(layer(idx), fh, indent=2, sort_keys=True)
        fh.write("\n")

runtime_overrides = {
    "overrides": [
        {
            "id": "ovr-canary-ledger-20260821",
            "status": "active",
            "release_id": "prod-2026.08.21.4",
            "cohort": "canary",
            "effective_from": "2026-08-21T16:30:00Z",
            "expires_at": "2026-08-22T16:30:00Z",
            "values": {"payments.dual_write_ledger": False},
        },
        {
            "id": "ovr-ledger-drill-20260810",
            "status": "expired",
            "release_id": "prod-2026.08.10.2",
            "cohort": "canary",
            "effective_from": "2026-08-10T09:00:00Z",
            "expires_at": "2026-08-10T10:00:00Z",
            "values": {"payments.dual_write_ledger": False},
        },
    ]
}
with open("flags/runtime-overrides.json", "w", encoding="utf-8") as fh:
    json.dump(runtime_overrides, fh, indent=2, sort_keys=True)
    fh.write("\n")

# ── flags/README.md ─────────────────────────────────────────────────────────
open("flags/README.md", "w", encoding="utf-8").write("""\
# Production flag configuration

This is the loader contract for release `prod-2026.08.21.4`, the release named
in `/data/deploy/production-snapshot.json`.

Three JSON layers live in this directory. A process loads them in the order
below, and each layer overrides the keys of the one before it:

    1. default.json    the baseline, loaded in every environment
    2. staging.json    loaded in staging AND in production
    3. prod.json       loaded in production only

`staging.json` is not a staging-only file. It was introduced as the shared
pre-production overlay back when we promoted one artefact from staging into
production, and the production loader has read it ever since. The filename is
historical and we have never renamed it. Development processes load
`default.json` on its own.

For production, the loader then reads the active override IDs listed for the
request's cohort in the production snapshot and applies their values last.
Entries in `runtime-overrides.json` that the snapshot does not name are not
active for this release, regardless of what value they contain.

A key that is absent from every active layer or override is not a load error.
The accessors in `app/platform/flags.py` and `app/web/src/shared/flags.ts` each
take a fallback argument and return it when the key cannot be resolved, so an
unknown key silently takes whatever value the call site passes.

Before lookup, the loader canonicalizes names through
`/data/app/platform/gate_registry.json`. Configuration uses canonical names;
shipping source may use a registered alias.

Values are plain JSON scalars — booleans for on/off gates, integers for
budgets, windows, sizes and timeouts.

Ownership lives in the service directories rather than here. Where a flag is
required to resolve to a particular value in production, the requirement is
recorded as a comment line beginning `PROD-REQUIREMENT:` next to the accessor
call. Those comment lines are the contract our platform review is held to.
""")

os.makedirs("deploy", exist_ok=True)
snapshot = {
    "as_of": "2026-08-21T18:00:00Z",
    "release_id": "prod-2026.08.21.4",
    "application_build_id": "app-2026.08.21.4",
    "config_bundle_id": "flags-2026.08.21.3",
    "cohorts": [
        {"name": "stable", "traffic_percent": 80, "active_override_ids": []},
        {
            "name": "canary",
            "traffic_percent": 20,
            "active_override_ids": ["ovr-canary-ledger-20260821"],
        },
    ],
}
with open("deploy/production-snapshot.json", "w", encoding="utf-8") as fh:
    json.dump(snapshot, fh, indent=2, sort_keys=True)
    fh.write("\n")

# Read-only deployment diagnostic emitted by the production resolver. It makes
# the active cohort merge inspectable without carrying requirement, liveness,
# alias, fallback or cleanup conclusions. Those still have to be derived from
# the shipping application and configuration artifacts.
base_values = {}
base_winners = {}
for flag in sorted({item[0] for item in LAYERS}):
    for layer_name, layer_index in (
        ("default.json", 0),
        ("staging.json", 1),
        ("prod.json", 2),
    ):
        table = layer(layer_index)
        if flag in table:
            base_values[flag] = table[flag]
            base_winners[flag] = layer_name

overrides_by_id = {item["id"]: item for item in runtime_overrides["overrides"]}
report_cohorts = {}
for cohort in snapshot["cohorts"]:
    values = dict(base_values)
    winners = dict(base_winners)
    for override_id in cohort["active_override_ids"]:
        for flag, value in overrides_by_id[override_id]["values"].items():
            values[flag] = value
            winners[flag] = f"runtime:{override_id}"
    report_cohorts[cohort["name"]] = {
        "active_override_ids": cohort["active_override_ids"],
        "gates": {
            flag: {"value": values[flag], "winning_layer": winners[flag]}
            for flag in sorted(values)
        },
        "traffic_percent": cohort["traffic_percent"],
    }

effective_report = {
    "application_build_id": snapshot["application_build_id"],
    "config_bundle_id": snapshot["config_bundle_id"],
    "generated_at": snapshot["as_of"],
    "release_id": snapshot["release_id"],
    "report_type": "read-only-production-resolver-export",
    "schema_version": 1,
    "cohorts": report_cohorts,
}
with open("deploy/effective-flag-report.json", "w", encoding="utf-8") as fh:
    json.dump(effective_report, fh, indent=2, sort_keys=True)
    fh.write("\n")

os.makedirs("docs", exist_ok=True)
open("docs/flag-layer-migration-draft.md", "w", encoding="utf-8").write("""\
# Flag layer simplification proposal

Status: draft
Approval: pending
Last updated: 2026-07-02
Target release: prod-2026.09.1

The proposed September loader removes the shared staging overlay from
production. Production would load `default.json`, then `prod.json`, and would
not apply cohort overrides. The rollout and approval fields will be completed
during release planning.

The billing PDF cleanup spreadsheet used during discovery still lists
`billing.legacy_invoice_pdf`, which is why the name appears in historical
material even if it is absent from the application build.
""")

# ── The application tree ────────────────────────────────────────────────────
# Files carrying flag references are literal. Nothing is templated into them,
# so the reference set is exactly what is written here.
FILES = {}

FILES["app/build-manifest.json"] = json.dumps({
    "application_build_id": "app-2026.08.21.4",
    "production_source_roots": ["platform", "services", "web/src"],
    "excluded_roots": ["tests", "docs", "examples"],
}, indent=2, sort_keys=True) + "\n"

FILES["app/platform/gate_registry.json"] = json.dumps({
    "schema_version": 1,
    "aliases": {"reporting.background_export": "reporting.async_export"},
}, indent=2, sort_keys=True) + "\n"

FILES["app/README.md"] = """\
# monolith services

    services/checkout        cart, express lane, pricing, session
    services/payments        ledger, settlement, tokenization, gateway
    services/billing         invoices, proration, dunning
    services/notifications   digest, push, templates
    services/search          query parsing, ranking, indexing
    services/reporting       exports, warehouse reads
    services/identity        mfa, sessions, passkeys
    services/ingest          batching, dead-letter replay
    platform/                flag accessors, shadowing, circuit breaker, shared helpers
    web/src/                 the browser bundle
    tests/                   unit tests

Runtime configuration, including every feature gate, is resolved out of
`/data/flags`. See the README there for the layer order. `build-manifest.json`
is the release inventory for production-shipping source; tests and historical
documents are not part of the deployed application.
"""

FILES["app/platform/flags.py"] = '''\
"""Flag accessors.

Layers are loaded in the order given by /data/flags/README.md. Later layers
override earlier ones. A key missing from every layer resolves to the fallback
supplied by the caller, which is why every accessor takes one.
"""
import functools
import json
import logging
import os

LOG = logging.getLogger(__name__)

DATA_ROOT = os.environ.get("DATA_ROOT", "/data")
FLAG_ROOT = os.path.join(DATA_ROOT, "flags")
LAYER_ORDER = ("default", "staging", "prod")


@functools.lru_cache(maxsize=1)
def _aliases():
    path = os.path.join(DATA_ROOT, "app", "platform", "gate_registry.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["aliases"]


def _canonical(name):
    return _aliases().get(name, name)


def _layers_for(environment):
    if environment == "development":
        return ("default",)
    if environment == "staging":
        return ("default", "staging")
    return LAYER_ORDER


@functools.lru_cache(maxsize=16)
def resolved(environment, cohort="stable"):
    merged = {}
    for name in _layers_for(environment):
        path = os.path.join(FLAG_ROOT, name + ".json")
        with open(path, encoding="utf-8") as fh:
            merged.update(json.load(fh))
    if environment == "production":
        snapshot_path = os.path.join(DATA_ROOT, "deploy", "production-snapshot.json")
        override_path = os.path.join(FLAG_ROOT, "runtime-overrides.json")
        with open(snapshot_path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        with open(override_path, encoding="utf-8") as fh:
            overrides = {item["id"]: item for item in json.load(fh)["overrides"]}
        selected = next(item for item in snapshot["cohorts"] if item["name"] == cohort)
        for override_id in selected["active_override_ids"]:
            merged.update(overrides[override_id]["values"])
    return merged


def _lookup(name, fallback):
    env = os.environ.get("APP_ENV", "production")
    cohort = os.environ.get("RELEASE_COHORT", "stable")
    table = resolved(env, cohort)
    canonical = _canonical(name)
    if canonical not in table:
        LOG.debug("flag not defined in any layer, using call-site fallback")
        return fallback
    return table[canonical]


def enabled(name, fallback=False):
    return bool(_lookup(name, fallback))


def get_bool(name, default=False):
    return bool(_lookup(name, default))


def get_int(name, default=0):
    return int(_lookup(name, default))


def feature(name, fallback=False):
    """Decorator form. Returns None instead of calling when the gate is off."""
    def outer(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            if not enabled(name, fallback):
                return None
            return fn(*args, **kwargs)
        return inner
    return outer
'''

FILES["app/platform/constants.py"] = '''\
"""Shared string constants.

Some gates are referenced through a constant rather than inline, so the literal
appears here and not at the call site.
"""

FLAG_ASYNC_EXPORT = "reporting.background_export"

EXPORT_MIME = "application/x-ndjson"
MAX_EXPORT_PARTS = 64
RETRY_BACKOFF_MS = (100, 400, 1600, 6400)
'''

FILES["app/platform/shadow.py"] = '''\
"""Request shadowing: replay a fraction of live traffic at the candidate."""
import logging

from platform import flags
from platform.hashing import bucket_of

LOG = logging.getLogger(__name__)
SHADOW_SAMPLE = 32


def should_shadow(request_id):
    if not flags.enabled("platform.request_shadowing"):
        return False
    return bucket_of(request_id) < SHADOW_SAMPLE


def shadow_headers(request_id, session):
    headers = {"X-Shadow": "1", "X-Request-Id": request_id}
    if flags.get_bool("identity.session_pinning", default=True):
        headers["X-Session-Pin"] = session.pin
    return headers
'''

FILES["app/platform/breaker.py"] = '''\
"""Per-dependency circuit breaker."""
import logging
import time

from platform import flags

LOG = logging.getLogger(__name__)


class Breaker:
    def __init__(self, dependency):
        self.dependency = dependency
        self.opened_at = None
        # window after which a tripped breaker is allowed one probe
        self.cooldown_ms = flags.get_int("platform.circuit_breaker_ms", default=1500)

    def trip(self):
        self.opened_at = time.monotonic()
        LOG.warning("breaker tripped")

    def allows(self):
        if self.opened_at is None:
            return True
        return (time.monotonic() - self.opened_at) * 1000 >= self.cooldown_ms
'''

FILES["app/services/checkout/express.py"] = '''\
"""The one-tap express lane."""
import logging

from platform import flags
from services.checkout.pricing import quote_for

LOG = logging.getLogger(__name__)


def express_available(basket, customer):
    if not flags.enabled("checkout.express_lane"):
        return False
    if basket.requires_age_check:
        return False
    return customer.has_default_card and len(basket.lines) <= 6


def express_quote(basket, customer):
    if not express_available(basket, customer):
        return None
    return quote_for(basket, customer, fast_path=True)
'''

FILES["app/services/checkout/cart.py"] = '''\
"""Basket assembly and the write-behind retry loop."""
import logging

from platform import flags
from platform.constants import RETRY_BACKOFF_MS

LOG = logging.getLogger(__name__)


def persist(basket, store):
    budget = flags.get_int("checkout.retry_budget", default=2)
    attempts = 0
    while attempts <= budget:
        try:
            return store.put(basket)
        except TimeoutError:
            attempts += 1
            if attempts > budget:
                raise
            _sleep_for(attempts)
    return None


def _sleep_for(attempt):
    idx = min(attempt - 1, len(RETRY_BACKOFF_MS) - 1)
    return RETRY_BACKOFF_MS[idx]
'''

FILES["app/services/checkout/session.py"] = '''\
"""Checkout session lifecycle."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
SESSION_TTL_S = 1800


def resume(session_id, store):
    budget = flags.get_int("checkout.retry_budget", default=2)
    for _ in range(budget + 1):
        session = store.load(session_id)
        if session is not None:
            return session
    LOG.info("session could not be resumed")
    return None


def expire_stale(store, now):
    return store.purge_older_than(now - SESSION_TTL_S)
'''

FILES["app/services/checkout/pricing.py"] = '''\
"""Quote construction."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def quote_for(basket, customer, fast_path=False):
    lines = [_line_price(line) for line in basket.lines]
    total = sum(lines)
    if flags.enabled("platform.request_shadowing"):
        LOG.debug("quote computed under shadowed traffic")
    return {"lines": lines, "total": total, "fast_path": fast_path}


def _line_price(line):
    return round(line.unit_price * line.quantity, 2)
'''

FILES["app/services/payments/ledger.py"] = '''\
"""Ledger writes.

The v2 ledger is being backfilled. Until the backfill finishes, production must
write to the legacy ledger only: a dual write against a partially populated v2
ledger produces balances that cannot be reconciled after the fact.
"""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def post(entry, legacy, ledger_v2):
    legacy.append(entry)
    # PROD-REQUIREMENT: payments.dual_write_ledger must resolve to false in
    # production until the PLAT-4471 backfill completes. Enabling it early
    # writes entries the v2 ledger cannot reconcile against its own history.
    if flags.get_bool("payments.dual_write_ledger", default=False):
        ledger_v2.append(_translate(entry))
    return entry.id


def _translate(entry):
    return {"id": entry.id, "amount_minor": int(round(entry.amount * 100)),
            "currency": entry.currency, "account": entry.account}
'''

FILES["app/services/payments/settlement.py"] = '''\
"""Nightly settlement batching."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def batches(pending):
    size = flags.get_int("payments.settlement_batch_size", default=200)
    for start in range(0, len(pending), size):
        yield pending[start:start + size]


def settle(pending, gateway):
    settled = 0
    for batch in batches(pending):
        settled += gateway.submit(batch)
    return settled
'''

FILES["app/services/payments/tokenization.py"] = '''\
"""Card tokenization."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def tokenize(card, vault):
    if flags.get_bool("payments.card_tokenization_v2", default=False):
        return vault.token_v2(card.pan, card.expiry)
    return vault.token_v1(card.pan)


def detokenize(token, vault):
    return vault.resolve(token)
'''

FILES["app/services/payments/gateway.py"] = '''\
"""Acquirer gateway adapter."""
import logging

from platform import flags
from platform.breaker import Breaker

LOG = logging.getLogger(__name__)


class Gateway:
    def __init__(self, transport):
        self.transport = transport
        self.breaker = Breaker("acquirer")

    def submit(self, batch):
        if not self.breaker.allows():
            LOG.warning("acquirer breaker open, batch deferred")
            return 0
        payload = [self._row(item) for item in batch]
        return self.transport.post(payload)

    def _row(self, item):
        row = {"ref": item.ref, "amount": item.amount}
        if flags.get_bool("payments.card_tokenization_v2", default=False):
            row["token_version"] = 2
        return row
'''

FILES["app/services/billing/invoices.py"] = '''\
"""Invoice assembly and rendering."""
import logging

from services.billing.proration import prorate

LOG = logging.getLogger(__name__)
PAGE_SIZE = "A4"


def build(subscription, period):
    lines = [_line(item, period) for item in subscription.items]
    return {"customer": subscription.customer_id, "period": period,
            "lines": lines, "total": round(sum(l["amount"] for l in lines), 2)}


def _line(item, period):
    return {"sku": item.sku, "amount": prorate(item, period)}


def render(invoice, renderer):
    return renderer.to_pdf(invoice, page_size=PAGE_SIZE)
'''

FILES["app/services/billing/proration.py"] = '''\
"""Mid-cycle proration."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def prorate(item, period):
    if flags.get_bool("billing.proration_v3", default=False):
        return _v3(item, period)
    return _v2(item, period)


def _v2(item, period):
    return round(item.rate * period.fraction, 2)


def _v3(item, period):
    whole = int(period.fraction * period.days)
    return round(item.rate * whole / period.days, 2)
'''

FILES["app/services/billing/dunning.py"] = '''\
"""Dunning schedule for failed collections."""
import logging

LOG = logging.getLogger(__name__)
SCHEDULE_DAYS = (1, 3, 7, 14, 21)


def next_attempt(failure_count):
    if failure_count >= len(SCHEDULE_DAYS):
        return None
    return SCHEDULE_DAYS[failure_count]


def should_suspend(failure_count):
    return failure_count > len(SCHEDULE_DAYS)
'''

FILES["app/services/notifications/digest.py"] = '''\
"""Digest batching for low-priority notifications."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def window_minutes():
    return flags.get_int("notifications.digest_window_minutes", default=30)


def bucket(events, now):
    width = window_minutes() * 60
    out = {}
    for event in events:
        key = int((now - event.created_at) // width)
        out.setdefault(key, []).append(event)
    return out
'''

FILES["app/services/notifications/push.py"] = '''\
"""Push delivery."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
QUIET_START_HOUR = 22
QUIET_END_HOUR = 7


def deliverable(now_hour):
    if not flags.get_bool("notifications.push_quiet_hours", default=True):
        return True
    return not (now_hour >= QUIET_START_HOUR or now_hour < QUIET_END_HOUR)


def send(token, payload, transport, now_hour):
    if not deliverable(now_hour):
        LOG.info("suppressed by quiet hours")
        return False
    return transport.push(token, payload)
'''

FILES["app/services/notifications/templates.py"] = '''\
"""Notification body templates."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def render(kind, context):
    body = _BODIES[kind].format(**context)
    if flags.get_bool("notifications.push_quiet_hours", default=True):
        body = body.rstrip()
    return body


_BODIES = {
    "receipt": "Thanks - your order {order_ref} is confirmed.",
    "shipped": "Order {order_ref} is on its way.",
    "failed": "We could not take payment for {order_ref}.",
}
'''

FILES["app/services/search/ranker.py"] = '''\
"""Result ranking."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
BM25_K1 = 1.2
BM25_B = 0.75


def rank(hits, query):
    scored = [(_bm25(hit, query), hit) for hit in hits]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    ordered = [hit for _, hit in scored]
    if flags.get_bool("search.semantic_rerank", default=False):
        ordered = _rerank(ordered, query)
    return ordered


def _bm25(hit, query):
    return sum(hit.term_frequency(term) * BM25_K1 for term in query.terms)


def _rerank(ordered, query):
    return sorted(ordered, key=lambda hit: -hit.embedding_similarity(query))
'''

FILES["app/services/search/query_parser.py"] = '''\
"""Query parsing."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


# PROD-REQUIREMENT: search.typo_tolerance must resolve to false in production.
# The fuzzy analyzer is not deployed to the production index, so a fuzzy clause
# is rejected by the query planner and the whole search 500s.
@flags.feature("search.typo_tolerance")
def fuzzy_clause(term):
    return {"fuzzy": {"title": {"value": term, "fuzziness": "AUTO"}}}


def parse(raw):
    terms = [t for t in raw.split() if t]
    clauses = []
    for term in terms:
        clause = fuzzy_clause(term)
        clauses.append(clause if clause is not None else {"term": {"title": term}})
    return {"bool": {"should": clauses}}
'''

FILES["app/services/search/indexer.py"] = '''\
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
'''

FILES["app/services/reporting/exporter.py"] = '''\
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
'''

FILES["app/services/reporting/warehouse.py"] = '''\
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
'''

FILES["app/services/identity/mfa.py"] = '''\
"""Multi-factor enrolment and grace periods."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def grace_expires_at(enrolled_at):
    # PROD-REQUIREMENT: identity.mfa_grace_hours must resolve to 0 in
    # production. Any non-zero grace window leaves accounts reachable with a
    # single factor, which our attestation forbids.
    hours = flags.get_int("identity.mfa_grace_hours", default=24)
    return enrolled_at + hours * 3600


def requires_second_factor(account, now):
    if account.mfa_enrolled:
        return True
    return now >= grace_expires_at(account.created_at)
'''

FILES["app/services/identity/session.py"] = '''\
"""Session issuance."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
TOKEN_TTL_S = 3600


def issue(account, request, signer):
    claims = {"sub": account.id, "ttl": TOKEN_TTL_S}
    if flags.get_bool("identity.session_pinning", default=True):
        claims["pin"] = _pin(request)
    return signer.sign(claims)


def _pin(request):
    return request.client_fingerprint
'''

FILES["app/services/identity/passkeys.py"] = '''\
"""Passkey enrolment."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
RP_NAME = "Acme"


def enrolment_options(account):
    if not flags.enabled("identity.passkey_enrolment"):
        return None
    return {"rp": {"name": RP_NAME}, "user": {"id": account.id},
            "authenticatorSelection": {"residentKey": "preferred"}}


def verify(attestation, verifier):
    return verifier.check(attestation)
'''

FILES["app/services/ingest/batcher.py"] = '''\
"""Inbound batching."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def chunk(rows):
    limit = flags.get_int("ingest.max_batch_rows", default=1000)
    for start in range(0, len(rows), limit):
        yield rows[start:start + limit]


def load(rows, sink):
    loaded = 0
    for part in chunk(rows):
        loaded += sink.copy(part)
    return loaded
'''

FILES["app/services/ingest/dead_letter.py"] = '''\
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
'''

FILES["app/web/src/shared/flags.ts"] = '''\
// Browser-side flag accessors. The bundle is served the merged layer set the
// server resolved, so the ordering rule in /data/flags/README.md already
// applies by the time this runs. A key the server could not resolve is absent
// from the payload and falls through to the caller's fallback.

declare const __FLAGS__: Record<string, boolean | number>;

export function isEnabled(name: string, fallback = false): boolean {
  const value = __FLAGS__[name];
  return value === undefined ? fallback : Boolean(value);
}

export function getNumber(name: string, fallback: number): number {
  const value = __FLAGS__[name];
  return typeof value === "number" ? value : fallback;
}
'''

FILES["app/web/src/search/resultsPanel.ts"] = '''\
import { isEnabled } from "../shared/flags";
import { skeletonRows } from "../shared/loaders";

// The panel renders a "sorted by relevance" affordance and suppresses the
// score column when the semantic reranker is in play, because the raw BM25
// score stops matching the displayed order.
export function renderResults(root: HTMLElement, hits: Hit[]): void {
  const reranked = isEnabled("search.semantic_rerank", true);
  root.replaceChildren(
    ...(hits.length === 0 ? skeletonRows(5) : hits.map((h) => row(h, reranked)))
  );
}

function row(hit: Hit, reranked: boolean): HTMLElement {
  const el = document.createElement("li");
  el.textContent = hit.title;
  if (!reranked) {
    el.dataset.score = hit.score.toFixed(3);
  }
  return el;
}

export interface Hit {
  title: string;
  score: number;
}
'''

FILES["app/web/src/checkout/expressLane.ts"] = '''\
import { isEnabled } from "../shared/flags";

export function mountExpressLane(root: HTMLElement): boolean {
  if (!isEnabled("checkout.express_lane")) {
    return false;
  }
  const button = document.createElement("button");
  button.textContent = "Buy now";
  button.className = "express-lane";
  root.append(button);
  return true;
}
'''

FILES["app/web/src/nav.ts"] = '''\
import { isEnabled } from "./shared/flags";

const LEGACY_ITEMS = ["Home", "Orders", "Account"];
const NEXT_ITEMS = ["Home", "Orders", "Subscriptions", "Account", "Help"];

export function navItems(): string[] {
  return isEnabled("web.new_nav") ? NEXT_ITEMS : LEGACY_ITEMS;
}
'''

FILES["app/web/src/app.ts"] = '''\
import { isEnabled } from "./shared/flags";
import { navItems } from "./nav";
import { mountExpressLane } from "./checkout/expressLane";

export function boot(root: HTMLElement): void {
  renderNav(root, navItems());
  mountExpressLane(root);
  if (isEnabled("identity.passkey_enrolment")) {
    promptPasskey(root);
  }
  if (isEnabled("web.new_nav")) {
    root.classList.add("nav-next");
  }
  if (!isEnabled("identity.session_pinning", true)) {
    root.dataset.pinned = "false";
  }
}

function renderNav(root: HTMLElement, items: string[]): void {
  const nav = document.createElement("nav");
  nav.append(...items.map((label) => link(label)));
  root.append(nav);
}

function link(label: string): HTMLElement {
  const a = document.createElement("a");
  a.textContent = label;
  return a;
}

function promptPasskey(root: HTMLElement): void {
  root.dataset.passkeyPrompt = "1";
}
'''

FILES["app/web/src/shared/loaders.ts"] = '''\
import { isEnabled } from "./flags";

export function skeletonRows(count: number): HTMLElement[] {
  if (!isEnabled("web.skeleton_loaders", true)) {
    return [];
  }
  return Array.from({ length: count }, () => {
    const el = document.createElement("li");
    el.className = "skeleton";
    return el;
  });
}
'''

FILES["app/tests/test_checkout_express.py"] = '''\
"""Express-lane gating."""
from platform import flags
from services.checkout import express


def test_express_off_by_default(monkeypatch, basket, customer):
    monkeypatch.setattr(flags, "enabled", lambda name, fallback=False: False)
    assert express.express_available(basket, customer) is False


def test_express_on(monkeypatch, basket, customer):
    monkeypatch.setattr(
        flags, "enabled",
        lambda name, fallback=False: name == "checkout.express_lane")
    assert express.express_available(basket, customer) is True
'''

FILES["app/tests/test_payments_ledger.py"] = '''\
"""Ledger dual-write gating."""
from platform import flags
from services.payments import ledger


def test_single_write(monkeypatch, entry, legacy, ledger_v2):
    monkeypatch.setattr(flags, "get_bool", lambda name, default=False: False)
    ledger.post(entry, legacy, ledger_v2)
    assert len(legacy) == 1 and len(ledger_v2) == 0


def test_dual_write(monkeypatch, entry, legacy, ledger_v2):
    monkeypatch.setattr(
        flags, "get_bool",
        lambda name, default=False: name == "payments.dual_write_ledger")
    ledger.post(entry, legacy, ledger_v2)
    assert len(legacy) == 1 and len(ledger_v2) == 1
'''

FILES["app/tests/test_dunning.py"] = '''\
"""Dunning schedule."""
from services.billing import dunning


def test_schedule_walks_forward():
    assert [dunning.next_attempt(i) for i in range(5)] == [1, 3, 7, 14, 21]


def test_schedule_exhausts():
    assert dunning.next_attempt(5) is None
    assert dunning.should_suspend(6) is True


def test_removed_pdf_gate_is_not_reintroduced():
    retired_gate = "billing.legacy_invoice_pdf"
    assert retired_gate not in dunning.__dict__
'''

# ── Filler modules ──────────────────────────────────────────────────────────
# Volume, so that "referenced nowhere" is a search rather than a glance. These
# reference no flags at all. Generated from a seeded stream in one fixed pass
# over a sorted list, so the output is stable across runs.
#
# No quoted dotted-lowercase string is ever emitted here: such a literal would
# look like a flag name to the read-back stage's extractor.
FILLER = [
    ("app/platform/hashing.py", "Stable bucketing helpers", ["bucket_of", "digest_of", "salted"]),
    ("app/platform/clock.py", "Monotonic and wall-clock helpers", ["now_ms", "elapsed_ms", "deadline_in"]),
    ("app/platform/retry.py", "Retry and backoff primitives", ["backoff_ms", "jittered", "attempts_for"]),
    ("app/platform/serde.py", "Serialisation helpers", ["to_row", "from_row", "coerce_scalar"]),
    ("app/services/checkout/__init__.py", "Checkout package", []),
    ("app/services/payments/__init__.py", "Payments package", []),
    ("app/services/billing/__init__.py", "Billing package", []),
    ("app/services/notifications/__init__.py", "Notifications package", []),
    ("app/services/search/__init__.py", "Search package", []),
    ("app/services/reporting/__init__.py", "Reporting package", []),
    ("app/services/identity/__init__.py", "Identity package", []),
    ("app/services/ingest/__init__.py", "Ingest package", []),
    ("app/platform/__init__.py", "Platform package", []),
    ("app/services/__init__.py", "Services package", []),
    ("app/services/checkout/inventory.py", "Availability lookups", ["in_stock", "reserve", "release"]),
    ("app/services/checkout/tax.py", "Tax computation", ["rate_for", "apply_tax", "exempt"]),
    ("app/services/payments/refunds.py", "Refund handling", ["refundable", "issue_refund", "reverse"]),
    ("app/services/payments/reconcile.py", "Acquirer reconciliation", ["match_rows", "unmatched", "summarise"]),
    ("app/services/billing/credits.py", "Credit notes", ["issue_credit", "apply_credit", "balance_of"]),
    ("app/services/notifications/webhooks.py", "Outbound webhooks", ["sign_body", "post_hook", "retryable"]),
    ("app/services/search/synonyms.py", "Synonym expansion", ["expand", "canonical", "load_pairs"]),
    ("app/services/search/highlight.py", "Snippet highlighting", ["snippet", "mark_terms", "trim_to"]),
    ("app/services/reporting/schedules.py", "Report schedules", ["due_now", "next_run", "cron_fields"]),
    ("app/services/identity/audit.py", "Identity audit trail", ["record", "recent_for", "purge_before"]),
    ("app/services/ingest/validate.py", "Row validation", ["validate_row", "reject_reason", "coerce"]),
    ("app/services/ingest/schema.py", "Inbound schema", ["columns_for", "widths", "nullable"]),
    ("app/platform/pagination.py", "Cursor pagination", ["encode_cursor", "decode_cursor", "page_of", "has_more"]),
    ("app/platform/metrics.py", "Counter and histogram helpers", ["incr", "observe", "timer_for", "snapshot"]),
    ("app/platform/idempotency.py", "Idempotency keys", ["key_for", "seen_before", "remember", "sweep"]),
    ("app/services/checkout/promotions.py", "Promotion codes", ["applicable", "discount_for", "stackable", "expired"]),
    ("app/services/checkout/addresses.py", "Address normalisation", ["normalise", "postcode_of", "country_of"]),
    ("app/services/payments/mandates.py", "Direct-debit mandates", ["active_for", "revoke", "next_collection"]),
    ("app/services/payments/fx.py", "Currency conversion", ["rate_between", "convert_minor", "rounding_mode"]),
    ("app/services/billing/statements.py", "Account statements", ["opening_balance", "movements", "closing_balance"]),
    ("app/services/billing/taxcodes.py", "Tax code registry", ["code_for", "reverse_charge", "zero_rated"]),
    ("app/services/notifications/preferences.py", "Per-account preferences", ["channels_for", "muted", "set_channel"]),
    ("app/services/search/facets.py", "Facet aggregation", ["buckets_for", "top_terms", "merge_facets"]),
    ("app/services/search/spelling.py", "Spelling suggestions", ["suggest", "edit_distance", "dictionary_hits"]),
    ("app/services/reporting/formats.py", "Export encodings", ["as_csv_rows", "as_ndjson_rows", "header_for"]),
    ("app/services/reporting/retention.py", "Report retention", ["expired_reports", "keep_until", "purge"]),
    ("app/services/identity/recovery.py", "Account recovery", ["challenge_for", "verify_answer", "lock_after"]),
    ("app/services/identity/devices.py", "Trusted devices", ["trusted", "register_device", "forget_device"]),
    ("app/services/ingest/watermarks.py", "Ingest watermarks", ["high_water", "advance", "lagging_partitions"]),
    ("app/services/ingest/dedupe.py", "Inbound dedupe", ["fingerprint", "already_seen", "record_seen"]),
]

VERBS = ["compute", "resolve", "collect", "normalise", "flatten", "merge", "select"]
NOUNS = ["rows", "keys", "buckets", "records", "tokens", "windows", "entries"]

for path, title, funcs in sorted(FILLER):
    body = ['"""%s."""' % title]
    if funcs:
        body.append("import logging")
        body.append("")
        body.append("LOG = logging.getLogger(__name__)")
        body.append("MAX_%s = %d" % (NOUNS[rng.randrange(len(NOUNS))].upper(),
                                     rng.choice([16, 32, 64, 128, 256, 512])))
        for fn in funcs:
            arg = NOUNS[rng.randrange(len(NOUNS))]
            verb = VERBS[rng.randrange(len(VERBS))]
            body.append("")
            body.append("")
            body.append("def %s(%s, limit=None):" % (fn, arg))
            body.append('    """%s the %s handed in."""' % (verb.capitalize(), arg))
            body.append("    kept = [item for item in %s if item is not None]" % arg)
            body.append("    if limit is not None:")
            body.append("        kept = kept[:limit]")
            body.append("    return kept")
    FILES[path] = "\n".join(body) + "\n"

for path, content in sorted(FILES.items()):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

print("built flags/ (4 files) and app/ (%d files)" % len(FILES))
BUILD

# ── READ-BACK STAGE ─────────────────────────────────────────────────────────
# Independent of the builder. It re-opens the three JSON layers, the README and
# every file under app/ from disk, extracts the flag universe from what is
# actually written there, and derives resolution, redundancy, dead flags,
# undefined names and PROD-REQUIREMENT outcomes from that. GROUND_TRUTH.md is
# whatever this stage prints.
python3 - <<'READBACK'
import json, os, re

LAYER_FILES = ["flags/default.json", "flags/staging.json", "flags/prod.json"]
layers = {os.path.basename(p): json.load(open(p, encoding="utf-8")) for p in LAYER_FILES}
DEFAULT, STAGING, PROD = layers["default.json"], layers["staging.json"], layers["prod.json"]

# Walk app/ and collect every file's text.
sources = {}
for root, dirs, files in os.walk("app"):
    dirs.sort()
    for name in sorted(files):
        path = os.path.join(root, name)
        sources[path] = open(path, encoding="utf-8").read()

# The flag universe comes from the artefacts, not from the builder: it is the
# union of the layer keys and every QUOTED string in app/ that looks like a flag
# name (lower_snake dotted, exactly one dot).
NAME_RE = re.compile(r"""['"]([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)['"]""")
from_source = set()
for text in sources.values():
    from_source.update(NAME_RE.findall(text))
defined = set(DEFAULT) | set(STAGING) | set(PROD)
universe = sorted(defined | from_source)

# Reference count: files under app/ whose text contains the literal name.
refs = {f: sorted(p for p, t in sources.items() if f in t) for f in universe}

def resolve(flag):
    """Production value + the layer it came from, per flags/README.md."""
    src, val = None, None
    for label, table in (("default.json", DEFAULT), ("staging.json", STAGING),
                         ("prod.json", PROD)):
        if flag in table:
            src, val = label, table[flag]
    return src, val

def jv(v):
    if v is None:
        return "(absent)"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)

def redundant_overrides(flag):
    """Overrides whose value equals the value they override."""
    out = []
    chain = [("default.json", DEFAULT), ("staging.json", STAGING), ("prod.json", PROD)]
    running = None
    for label, table in chain:
        if flag in table:
            if running is not None and table[flag] == running and label != "default.json":
                out.append(label)
            running = table[flag]
    return out

# PROD-REQUIREMENT blocks are read line by line rather than with one regex: the
# comment continues onto following lines, each of which carries its own comment
# marker, so the markers have to be stripped before the sentence can be read.
def _comment_body(line):
    s = line.strip()
    for marker in ("#", "//"):
        if s.startswith(marker):
            return s[len(marker):].strip()
    return None

reqs = []
for path in sorted(sources):
    lines = sources[path].splitlines()
    for i, line in enumerate(lines):
        body = _comment_body(line)
        if not body or "PROD-REQUIREMENT:" not in body:
            continue
        blob = [body.split("PROD-REQUIREMENT:", 1)[1].strip()]
        for nxt in lines[i + 1:]:
            more = _comment_body(nxt)
            if more is None:
                break
            blob.append(more)
        sentence = " ".join(" ".join(blob).split())
        nm = re.match(r"([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)", sentence)
        want = re.search(r"must resolve to (\S+?) in production", sentence)
        if nm and want:
            reqs.append((nm.group(1), want.group(1).rstrip("."), path))

out = []
w = out.append
w("# GROUND_TRUTH.md — flag-precedence-conflict")
w("")
w("Every value below was read **back out of the built artefacts** by the read-back")
w("stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file). The")
w("three JSON layers were re-parsed from disk, `app/` was walked file by file, and")
w("the flag universe was extracted from the layer keys plus every quoted")
w("flag-shaped string found in the source. Nothing here comes from the builder's")
w("in-memory tables.")
w("")
w("## Shape")
w("")
w(f"- layer files: `{'`, `'.join(os.path.basename(p) for p in LAYER_FILES)}` plus `flags/README.md`")
w(f"- keys in `default.json`: **{len(DEFAULT)}**")
w(f"- keys in `staging.json`: **{len(STAGING)}**")
w(f"- keys in `prod.json`: **{len(PROD)}**")
w(f"- distinct flags defined in at least one layer: **{len(defined)}**")
w(f"- distinct flag-shaped names appearing anywhere (layers + source): **{len(universe)}**")
w(f"- files under `app/`: **{len(sources)}**")
w(f"- total bytes under `app/`: **{sum(len(t.encode()) for t in sources.values()):,}**")
langs = {}
for p in sources:
    langs[os.path.splitext(p)[1] or "(none)"] = langs.get(os.path.splitext(p)[1] or "(none)", 0) + 1
w("- files by extension: " + ", ".join(f"{k} {v}" for k, v in sorted(langs.items())))
w("")
w("### Resolution order as stated in `flags/README.md`")
w("")
readme = open("flags/README.md", encoding="utf-8").read()
w("```")
for line in readme.splitlines():
    if line.strip().startswith(("1.", "2.", "3.")):
        w(line)
w("```")
w("")
w("`staging.json` is loaded in production as well as in staging. That sentence is")
w("in the README and nowhere else, and it is what makes the production value of a")
w("flag absent from `prod.json` non-obvious.")
w("")

# ── the full resolution table ──
w("## Full production resolution")
w("")
w("| flag | default.json | staging.json | prod.json | production value | winning layer | files in `app/` referencing it |")
w("|---|---|---|---|---|---|---:|")
for f in universe:
    src, val = resolve(f)
    w(f"| `{f}` | {jv(DEFAULT.get(f))} | {jv(STAGING.get(f))} | {jv(PROD.get(f))} | "
      f"{jv(val) if src else '**(undefined)**'} | {src or '**none**'} | {len(refs[f])} |")
w("")
by_layer = {}
for f in defined:
    src, _ = resolve(f)
    by_layer[src] = by_layer.get(src, 0) + 1
w("Where the production value comes from, across the "
  f"**{len(defined)}** defined flags:")
w("")
for label in ("prod.json", "staging.json", "default.json"):
    w(f"- `{label}`: **{by_layer.get(label, 0)}** flags")
w("")
leaks = sorted(f for f in defined if resolve(f)[0] == "staging.json")
w(f"The **{len(leaks)}** flags whose production value is set by `staging.json` alone "
  f"(present in staging, absent from prod):")
w("")
for f in leaks:
    w(f"- `{f}` → {jv(resolve(f)[1])}")
w("")
absent_prod = sorted(f for f in universe if f not in PROD)
w(f"Names absent from `prod.json`: **{len(absent_prod)}** — "
  + ", ".join(f"`{f}`" for f in absent_prod))
w("")
w("Reading `prod.json` on its own therefore leaves that many flags looking")
w("unset, which is the trap: only one of them is genuinely undefined.")
w("")

# ── PROD-REQUIREMENT audit ──
w("## Documented production requirements")
w("")
w(f"`PROD-REQUIREMENT:` comment lines found in `app/`: **{len(reqs)}**")
w("")
w("| flag | required production value | actual production value | verdict | recorded in |")
w("|---|---|---|---|---|")
violated = []
for flag, want, path in sorted(reqs):
    src, val = resolve(flag)
    actual = jv(val) if src else "(undefined)"
    ok = actual == want
    if not ok:
        violated.append((flag, want, actual, path))
    w(f"| `{flag}` | {want} | {actual} | {'satisfied' if ok else '**VIOLATED**'} | `{path}` |")
w("")
w(f"requirements violated: **{len(violated)}**")
for flag, want, actual, path in violated:
    src, _ = resolve(flag)
    w("")
    w(f"- **`{flag}`** is required to resolve to `{want}` in production and actually")
    w(f"  resolves to `{actual}`. It is absent from `prod.json`; the value comes from")
    w(f"  `{src}`, which production also loads. Default layer value: "
      f"{jv(DEFAULT.get(flag))}. Requirement recorded in `{path}`.")
w("")

# ── dead flags ──
w("## Dead flags — defined in a layer, referenced nowhere in `app/`")
w("")
dead = sorted(f for f in defined if not refs[f])
w(f"count: **{len(dead)}**")
for f in dead:
    w("")
    w(f"- **`{f}`** — default {jv(DEFAULT.get(f))}, staging {jv(STAGING.get(f))}, "
      f"prod {jv(PROD.get(f))}; resolves to {jv(resolve(f)[1])} in production; "
      f"**0** files under `app/` contain the string.")
all_three = sorted(f for f in defined if f in DEFAULT and f in STAGING and f in PROD)
w("")
w(f"Flags defined in **all three** layers: **{len(all_three)}** — "
  + ", ".join(f"`{f}`" for f in all_three))
w("")
w("So \"present in every layer\" does not isolate the dead flag; the reference")
w("count does. Of those flags defined in all three layers, the reference counts are:")
w("")
for f in all_three:
    w(f"- `{f}`: {len(refs[f])}")
w("")
once = sorted(f for f in defined if len(refs[f]) == 1)
w(f"Flags referenced in exactly **one** file under `app/`: **{len(once)}** — "
  + ", ".join(f"`{f}`" for f in once))
w("")
w("Those are the false positives an incomplete search produces: each is live and")
w("each is reachable only by finding a single file.")
w("")
indirect = sorted(f for f in defined
                  if refs[f] and all("constants.py" in p for p in refs[f]))
if indirect:
    for f in indirect:
        w(f"`{f}` is the sharpest of them: its only literal occurrence is the constant")
        w(f"definition in `{refs[f][0]}`, and the call site uses the constant name")
        w("rather than the string. A search restricted to accessor call sites finds")
        w("no call site for it at all.")
    w("")

# ── referenced but undefined ──
w("## Referenced but undefined")
w("")
undef = sorted(f for f in from_source if f not in defined)
w(f"count: **{len(undef)}**")
for f in undef:
    w("")
    w(f"- **`{f}`** — absent from all three layers. Referenced in "
      f"**{len(refs[f])}** files:")
    for p in refs[f]:
        text = sources[p]
        for line in text.splitlines():
            if f in line:
                w(f"  - `{p}`: `{line.strip()}`")
    w("")
    w("  Per `flags/README.md` an unresolvable key returns the fallback the call")
    w("  site passes, so this flag has no single production value: it takes a")
    w("  different one on each side.")
w("")

# ── redundant overrides ──
w("## Redundant overrides — an override equal to the value it overrides")
w("")
red = {f: redundant_overrides(f) for f in defined}
red = {f: v for f, v in red.items() if v}
w(f"flags carrying at least one redundant override: **{len(red)}**")
for f in sorted(red):
    w("")
    w(f"- **`{f}`** — default {jv(DEFAULT.get(f))}, staging {jv(STAGING.get(f))}, "
      f"prod {jv(PROD.get(f))}. Redundant layers: {', '.join('`'+x+'`' for x in red[f])}.")
    w(f"  Production value {jv(resolve(f)[1])}, identical to the baseline. Deleting")
    w(f"  both override entries changes nothing. Referenced in {len(refs[f])} file"
      f"{'' if len(refs[f]) == 1 else 's'} ({', '.join('`'+p+'`' for p in refs[f])}), so it")
    w("  is live code — it is neither dead nor undefined.")
w("")
w("### Near miss: production restores the baseline value over a staging override")
w("")
restores, inert = [], []
for f in sorted(defined):
    if f in DEFAULT and f in STAGING and f in PROD:
        if PROD[f] == DEFAULT[f] and STAGING[f] != DEFAULT[f]:
            (restores if refs[f] else inert).append(f)
w(f"count, restricted to flags the source actually reads: **{len(restores)}**")
w("")
w("| flag | default | staging | prod | production value | prod entry load-bearing? |")
w("|---|---|---|---|---|---|")
for f in restores:
    w(f"| `{f}` | {jv(DEFAULT[f])} | {jv(STAGING[f])} | {jv(PROD[f])} | "
      f"{jv(PROD[f])} | **yes** — deleting it would let {jv(STAGING[f])} apply |")
w("")
w("These look like the redundant case — production value equal to the baseline —")
w("but their production entries are load-bearing, because the staging layer would")
w("otherwise win. They must not be reported as redundant.")
if inert:
    w("")
    w("The same value shape also holds for "
      + ", ".join(f"`{f}`" for f in inert)
      + ", but that flag is dead: no source file reads it, so its production entry")
    w("bears nothing. It belongs to the dead-flag finding, not to this one.")
w("")
w("## Numbers that appear in no claim")
w("")
w("The filler modules under `app/` reference no flags. Their function names and")
w("constants are generated from a seeded stream and nothing about them is")
w("asserted; they exist so that the reference search covers a realistic amount of")
w("code.")

open("GROUND_TRUTH.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

# The V2 audit is a separate program that re-opens the deployment snapshot,
# runtime overrides, shipping manifest, alias registry and every shipping source
# file. It overwrites the legacy three-layer report above with the full result.
python3 audit_fixture.py . >/dev/null

echo "--- artefact sizes ---"
wc -c flags/*.json flags/README.md deploy/*.json docs/*.md GROUND_TRUTH.md GROUND_TRUTH.json
echo "app/ files: $(find app -type f | wc -l)   bytes: $(find app -type f -exec cat {} + | wc -c)"
echo "--- checksums ---"
find flags app deploy docs -type f | sort | xargs sha256sum | sha256sum
sha256sum flags/default.json flags/staging.json flags/prod.json flags/runtime-overrides.json flags/README.md deploy/production-snapshot.json deploy/effective-flag-report.json
