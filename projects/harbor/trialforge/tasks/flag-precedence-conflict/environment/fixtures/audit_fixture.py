#!/usr/bin/env python3
"""Independent read-back audit for the flag-precedence-conflict fixture.

This module imports nothing from build_fixture.sh. It derives the answer from
the files that the builder emitted, then writes author-only ground truth beside
the builder. Docker copies only the agent-facing subdirectories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


NAME_RE = re.compile(r"['\"]([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)['\"]")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def display(value):
    if value is None:
        return "(absent)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def parse_scalar(value: str):
    value = value.rstrip(".")
    if value == "true":
        return True
    if value == "false":
        return False
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return value


def comment_body(line: str):
    stripped = line.strip()
    for marker in ("#", "//"):
        if stripped.startswith(marker):
            return stripped[len(marker) :].strip()
    return None


def tree_hash(root: Path, relative_paths: list[Path]):
    digest = hashlib.sha256()
    for path in sorted(relative_paths):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def audit(root: Path):
    root = root.resolve()
    app_root = root / "app"
    layers = {
        name: load_json(root / "flags" / name)
        for name in ("default.json", "staging.json", "prod.json")
    }
    default = layers["default.json"]
    staging = layers["staging.json"]
    prod = layers["prod.json"]
    defined = set().union(*layers.values())

    snapshot = load_json(root / "deploy" / "production-snapshot.json")
    effective_report = load_json(root / "deploy" / "effective-flag-report.json")
    overrides_doc = load_json(root / "flags" / "runtime-overrides.json")
    overrides = {item["id"]: item for item in overrides_doc["overrides"]}
    manifest = load_json(app_root / "build-manifest.json")
    registry = load_json(app_root / "platform" / "gate_registry.json")
    aliases = registry["aliases"]

    shipping_paths = []
    for source_root in manifest["production_source_roots"]:
        base = app_root / source_root
        shipping_paths.extend(path for path in base.rglob("*") if path.is_file())
    shipping_paths = sorted(set(shipping_paths))

    # Registry data defines name normalization; it is not itself a call site.
    callsite_paths = [
        path for path in shipping_paths if path != app_root / "platform" / "gate_registry.json"
    ]
    source_text = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in callsite_paths
    }
    namespaces = {name.split(".", 1)[0] for name in defined}
    refs = defaultdict(set)
    raw_refs = defaultdict(set)
    for path, text in source_text.items():
        for raw in NAME_RE.findall(text):
            if raw.split(".", 1)[0] not in namespaces and raw not in aliases:
                continue
            canonical = aliases.get(raw, raw)
            refs[canonical].add(path)
            raw_refs[raw].add(path)

    referenced = set(refs)
    dead = sorted(defined - referenced)
    undefined = sorted(referenced - defined)

    base_values = {}
    base_winners = {}
    for flag in sorted(defined):
        for layer_name in ("default.json", "staging.json", "prod.json"):
            if flag in layers[layer_name]:
                base_values[flag] = layers[layer_name][flag]
                base_winners[flag] = layer_name

    cohort_values = {}
    cohort_winners = {}
    cohort_counts = {}
    cohort_staging = {}
    for cohort in snapshot["cohorts"]:
        name = cohort["name"]
        values = dict(base_values)
        winners = dict(base_winners)
        for override_id in cohort["active_override_ids"]:
            override = overrides[override_id]
            assert override["status"] == "active"
            assert override["release_id"] == snapshot["release_id"]
            assert override["cohort"] == name
            for flag, value in override["values"].items():
                assert flag in defined
                values[flag] = value
                winners[flag] = f"runtime:{override_id}"
        cohort_values[name] = values
        cohort_winners[name] = winners
        cohort_counts[name] = dict(sorted(Counter(winners.values()).items()))
        cohort_staging[name] = sorted(
            flag for flag, winner in winners.items() if winner == "staging.json"
        )

    requirements = []
    for path in sorted(source_text):
        lines = source_text[path].splitlines()
        for index, line in enumerate(lines):
            body = comment_body(line)
            if not body or "PROD-REQUIREMENT:" not in body:
                continue
            parts = [body.split("PROD-REQUIREMENT:", 1)[1].strip()]
            for following in lines[index + 1 :]:
                more = comment_body(following)
                if more is None:
                    break
                parts.append(more)
            sentence = " ".join(" ".join(parts).split())
            name_match = re.match(r"([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)", sentence)
            value_match = re.search(r"must resolve to (\S+?) in production", sentence)
            if name_match and value_match:
                requirements.append(
                    {
                        "flag": aliases.get(name_match.group(1), name_match.group(1)),
                        "required": parse_scalar(value_match.group(1)),
                        "path": path,
                    }
                )

    violations = {}
    for cohort in snapshot["cohorts"]:
        name = cohort["name"]
        violations[name] = [
            {
                **requirement,
                "actual": cohort_values[name].get(requirement["flag"]),
            }
            for requirement in requirements
            if cohort_values[name].get(requirement["flag"]) != requirement["required"]
        ]
    violating_flags = sorted(
        {item["flag"] for cohort_items in violations.values() for item in cohort_items}
    )
    exposure = {
        flag: sum(
            cohort["traffic_percent"]
            for cohort in snapshot["cohorts"]
            if any(item["flag"] == flag for item in violations[cohort["name"]])
        )
        for flag in violating_flags
    }

    fallback_evidence = []
    for path, text in source_text.items():
        if "search.semantic_rerank" not in text:
            continue
        for line in text.splitlines():
            if "search.semantic_rerank" in line:
                fallback_evidence.append({"path": path, "line": line.strip()})

    baseline_restores = []
    for flag in sorted(defined):
        if flag not in default or flag not in staging or flag not in prod:
            continue
        if prod[flag] != default[flag] or staging[flag] == default[flag]:
            continue
        baseline_restores.append(
            {
                "flag": flag,
                "default": default[flag],
                "staging": staging[flag],
                "prod": prod[flag],
                "shipping_live": flag in referenced,
                "removal_changes_resolved_value": True,
                "removal_changes_behaviour": flag in referenced,
            }
        )
    digest = "notifications.digest_window_minutes"
    redundant = {
        "flag": digest,
        "default": default[digest],
        "staging": staging[digest],
        "prod": prod[digest],
        "shipping_live": digest in referenced,
        "removing_staging_and_prod_changes_resolved_value": False,
        "removing_staging_and_prod_changes_behaviour": False,
    }

    current_doc = (root / "flags" / "README.md").read_text(encoding="utf-8")
    draft_doc = (root / "docs" / "flag-layer-migration-draft.md").read_text(encoding="utf-8")
    agent_paths = [
        path
        for directory in ("flags", "app", "deploy", "docs")
        for path in (root / directory).rglob("*")
        if path.is_file()
    ]

    expected_report_cohorts = {
        cohort["name"]: {
            "active_override_ids": cohort["active_override_ids"],
            "gates": {
                flag: {
                    "value": cohort_values[cohort["name"]][flag],
                    "winning_layer": cohort_winners[cohort["name"]][flag],
                }
                for flag in sorted(cohort_values[cohort["name"]])
            },
            "traffic_percent": cohort["traffic_percent"],
        }
        for cohort in snapshot["cohorts"]
    }
    report_matches_derived = (
        effective_report.get("release_id") == snapshot["release_id"]
        and effective_report.get("application_build_id")
        == snapshot["application_build_id"]
        and effective_report.get("config_bundle_id") == snapshot["config_bundle_id"]
        and effective_report.get("generated_at") == snapshot["as_of"]
        and effective_report.get("cohorts") == expected_report_cohorts
    )

    result = {
        "snapshot": snapshot,
        "layer_key_counts": {name: len(table) for name, table in layers.items()},
        "defined_gate_count": len(defined),
        "shipping_file_count": len(shipping_paths),
        "shipping_roots": manifest["production_source_roots"],
        "excluded_roots": manifest["excluded_roots"],
        "agent_facing_tree_sha256": tree_hash(root, agent_paths),
        "aliases": aliases,
        "raw_reference_files": {name: sorted(paths) for name, paths in sorted(raw_refs.items())},
        "canonical_reference_files": {
            name: sorted(paths) for name, paths in sorted(refs.items())
        },
        "dead_configured_gates": dead,
        "undefined_canonical_gates": undefined,
        "cohort_values": cohort_values,
        "cohort_winners": cohort_winners,
        "cohort_layer_counts": cohort_counts,
        "cohort_staging_inheritances": cohort_staging,
        "effective_report_matches_derived_resolution": report_matches_derived,
        "requirements": requirements,
        "violations_by_cohort": violations,
        "violating_gate_names": violating_flags,
        "violation_traffic_exposure_percent": exposure,
        "undefined_fallback_evidence": fallback_evidence,
        "redundant_override": redundant,
        "baseline_restoring_prod_entries": baseline_restores,
        "provenance": {
            "snapshot_release_id": snapshot["release_id"],
            "snapshot_as_of": snapshot["as_of"],
            "current_readme_names_release": snapshot["release_id"] in current_doc,
            "draft_marked_unapproved": "Approval: pending" in draft_doc,
            "draft_targets_other_release": snapshot["release_id"] not in draft_doc,
        },
    }
    return result


def write_markdown(result, path: Path):
    lines = [
        "# GROUND_TRUTH.md - flag-precedence-conflict V3",
        "",
        "Derived independently from the emitted agent-facing files by `audit_fixture.py`.",
        "The builder's in-memory tables are not imported.",
        "",
        "## Authority and shipping scope",
        "",
        f"- snapshot: `{result['snapshot']['release_id']}` at `{result['snapshot']['as_of']}`",
        f"- shipping roots: {', '.join('`' + x + '`' for x in result['shipping_roots'])}",
        f"- excluded roots: {', '.join('`' + x + '`' for x in result['excluded_roots'])}",
        f"- shipping files: **{result['shipping_file_count']}**",
        f"- agent-facing tree SHA-256: `{result['agent_facing_tree_sha256']}`",
        "- current README matches the snapshot release; the migration note is pending and targets another release",
        "- the read-only resolver export matches an independent layer-and-override derivation",
        "",
        "## Cohort resolution",
        "",
    ]
    for cohort in result["snapshot"]["cohorts"]:
        name = cohort["name"]
        counts = result["cohort_layer_counts"][name]
        counts_text = ", ".join(f"{layer} {count}" for layer, count in counts.items())
        inherited = ", ".join(result["cohort_staging_inheritances"][name])
        lines.extend(
            [
                f"- **{name} ({cohort['traffic_percent']}%)**: {counts_text}",
                f"  - staging winners: {inherited}",
            ]
        )
    lines.extend(
        [
            "",
            "## Requirements",
            "",
            f"- documented shipping-source requirements: **{len(result['requirements'])}**",
            f"- violating canonical gates: **{len(result['violating_gate_names'])}**: "
            + ", ".join(f"`{x}`" for x in result["violating_gate_names"]),
        ]
    )
    for flag, percent in result["violation_traffic_exposure_percent"].items():
        stable = result["cohort_values"]["stable"][flag]
        canary = result["cohort_values"]["canary"][flag]
        lines.append(
            f"- `{flag}` is stable `{display(stable)}`, canary `{display(canary)}`; violation exposure **{percent}%**"
        )
    lines.extend(
        [
            "",
            "## Shipping liveness",
            "",
            "- dead configured canonical gates: "
            + ", ".join(f"`{x}`" for x in result["dead_configured_gates"]),
            "- undefined canonical gates read by shipping code: "
            + ", ".join(f"`{x}`" for x in result["undefined_canonical_gates"]),
            "- alias: `reporting.background_export` -> `reporting.async_export`; the canonical gate is live",
            "- `billing.legacy_invoice_pdf` occurs only outside the manifest's shipping roots",
            "",
            "### Undefined fallback evidence",
            "",
        ]
    )
    for item in result["undefined_fallback_evidence"]:
        lines.append(f"- `{item['path']}`: `{item['line']}`")
    lines.extend(
        [
            "",
            "## Cleanup taxonomy",
            "",
            "- `notifications.digest_window_minutes`: removing staging and prod changes neither the resolved value nor behaviour",
            "- `billing.legacy_invoice_pdf`: removing prod changes the resolved value from false to true, but no shipping behaviour",
            "- live baseline-restoring prod entries whose removal changes both value and behaviour:",
        ]
    )
    for item in result["baseline_restoring_prod_entries"]:
        if item["shipping_live"]:
            lines.append(f"  - `{item['flag']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(result):
    assert result["layer_key_counts"] == {
        "default.json": 21,
        "staging.json": 15,
        "prod.json": 13,
    }
    assert result["defined_gate_count"] == 21
    assert result["cohort_layer_counts"]["stable"] == {
        "default.json": 2,
        "prod.json": 13,
        "staging.json": 6,
    }
    canary_counts = result["cohort_layer_counts"]["canary"]
    assert canary_counts["default.json"] == 2
    assert canary_counts["prod.json"] == 13
    assert canary_counts["staging.json"] == 5
    assert sum(value for key, value in canary_counts.items() if key.startswith("runtime:")) == 1
    assert result["effective_report_matches_derived_resolution"] is True
    assert result["violating_gate_names"] == ["payments.dual_write_ledger"]
    assert result["violation_traffic_exposure_percent"] == {
        "payments.dual_write_ledger": 80
    }
    assert result["dead_configured_gates"] == ["billing.legacy_invoice_pdf"]
    assert result["undefined_canonical_gates"] == ["search.semantic_rerank"]
    assert result["aliases"] == {
        "reporting.background_export": "reporting.async_export"
    }
    assert len(result["undefined_fallback_evidence"]) == 2
    restores = {
        item["flag"]: item["shipping_live"]
        for item in result["baseline_restoring_prod_entries"]
    }
    assert restores == {
        "billing.legacy_invoice_pdf": False,
        "identity.session_pinning": True,
        "notifications.push_quiet_hours": True,
        "platform.request_shadowing": True,
        "web.new_nav": True,
    }
    assert all(result["provenance"].values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).parent)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    result = audit(args.root)
    validate(result)
    if not args.check_only:
        (args.root / "GROUND_TRUTH.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_markdown(result, args.root / "GROUND_TRUTH.md")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
