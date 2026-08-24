#!/bin/bash
set -euo pipefail

mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Security release decision — cutoff 2026-08-17 18:00 UTC

Decision: APPROVE `v1.0.0-rc1` for controlled promotion. Quarantine and replace
all deployments of `v0.8.0` through `v0.9.1`. The cutoff deployment snapshot,
resolved by image digest through the immutable Git manifest, assigns 16, 14,
12, 10 and 12 workspaces respectively to v0.8.0, v0.8.1, v0.9.0, v0.9.1 and
v1.0.0-rc1. The first four variants therefore potentially exposed 52
workspaces. Receipt labels lag the digest for WS-0002, WS-0018, WS-0035,
WS-0044, WS-0053 and WS-0060; those labels are not deployment authority.

Contract and implementation history

Safe replacement reads SOURCE before touching TARGET, then transactionally
replaces the target directory entry. It never writes through an existing or
broken link or creates/changes the link referent; SOURCE stays byte-identical;
a source-read or pre-commit failure leaves TARGET unchanged and no partial/temp
file; an existing regular target keeps its mode; and a missing or symbolic-link
target becomes a regular 0600 file.

- `replace-v0.8.0`: direct `open(target, "w")` follows existing/broken links and
  creates missing files as 0644. Unsafe.
- `replace-v0.8.1`: check/unlink/direct-open leaves a check/use link-swap race
  and recreates new or existing targets as 0644. Unsafe.
- `replace-v0.9.0`: temp plus `os.replace` is link-, source- and failure-safe,
  but does not carry an existing mode; the 0600 temp resets established modes.
  Unsafe to ship under the contract.
- `replace-v0.9.1`: `os.replace(source, target)` removes SOURCE and transfers its
  mode to TARGET. Unsafe.
- `replace-v1.0.0-rc1`: reads SOURCE first and uses upstream `rewrite()` at
  pinned python-dotenv SHA 751f8c148222e58aa173c83c4e5e6cfccb2cc124.
  Its temp-and-replace transaction preserves regular-target modes, creates
  missing or prior-link targets 0600, does not modify link referents, cleans up on
  failure, and never moves SOURCE.

Run reconciliation

There are 180 attempt-registry/log entries but 174 logical operation IDs and
174 terminal receipts. Six operations were retried once, so the six extra
attempts are not separate replacements or impacts.

Terminal impact, derived from each operation's preflight state versus receipt:

- Existing-link referent overwritten (referent hash changed): WS-0002, WS-0004,
  WS-0007, WS-0011.
- Broken-link referent created (absent hash became present): WS-0003, WS-0009,
  WS-0013.
- Link-check race overwrite (regular at preflight; post-check symlink and outside
  referent write): WS-0018, WS-0027.
- Missing target created regular 0644: WS-0004, WS-0006, WS-0010, WS-0012,
  WS-0017, WS-0024, WS-0029.
- Existing regular target mode changed from preflight 0640 to terminal 0644:
  WS-0018, WS-0020, WS-0048; from preflight 0640 to terminal 0600: WS-0035.
- SOURCE present before but missing after: WS-0044, WS-0048, WS-0051.

Those sets deduplicate to 20 actually affected workspaces:
WS-0002, WS-0003, WS-0004, WS-0006, WS-0007, WS-0009, WS-0010, WS-0011,
WS-0012, WS-0013, WS-0017, WS-0018, WS-0020, WS-0024, WS-0027, WS-0029,
WS-0035, WS-0044, WS-0048, WS-0051.

The remaining 32 assigned to unsafe images were exposed but have no observed
contract-impacting terminal change: WS-0001, WS-0005, WS-0008, WS-0014,
WS-0015, WS-0016, WS-0019, WS-0021, WS-0022, WS-0023, WS-0025, WS-0026,
WS-0028, WS-0030, WS-0031, WS-0032, WS-0033, WS-0034, WS-0036, WS-0037,
WS-0038, WS-0039, WS-0040, WS-0041, WS-0042, WS-0043, WS-0045, WS-0046,
WS-0047, WS-0049, WS-0050, WS-0052.

Candidate evidence

All 12 candidate assignments, WS-0053 through WS-0064, are unaffected. The
terminal evidence covers existing links (WS-0053/0054), broken links
(WS-0055/0056), new targets created 0600 (WS-0057/0058), existing 0640 targets
preserved (WS-0059/0060), and unreadable SOURCE failures leaving TARGET intact
(WS-0061/0062), plus ordinary success cases. Existing/broken referents stayed
unchanged and all readable sources remained present.

Required remediation

1. Stop and roll back v0.8.0-v0.9.1, then redeploy the reviewed candidate; do
   not treat stale receipt labels as proof that an unsafe digest is gone.
2. Restore overwritten/created outside-workspace referents for the link and race
   sets from backup to their preflight hashes; inspect the outside paths and
   rotate every secret whose content crossed the workspace boundary.
3. Set every insecure new target to 0600. Restore each existing target to its
   recorded preflight mode (0640 here), even when the change was more
   restrictive; rotate secrets for any interval in which a target was 0644.
4. Recreate the missing SOURCE files for WS-0044, WS-0048 and WS-0051 from the
   terminal target or backup, verify against the preflight source hashes, and
   independently verify the intended target content and permissions.
5. Promote rc1 through the same canary matrix, monitor source/target/referent
   hashes and modes, and close the incident only after every restoration and
   rotation has read-back evidence.
EOF
