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
