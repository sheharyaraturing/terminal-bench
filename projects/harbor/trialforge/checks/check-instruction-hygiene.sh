#!/usr/bin/env bash
# The instruction must read as a natural persona request.
#
# CONTRIBUTING.md: names no tool and no server, not once. The agent must work
# out the toolchain itself. It also must not leak grader machinery (fourth
# wall). Pure greps over instruction.md - no parsing needed.
set -u

TASK="${1:?usage: check-instruction-hygiene.sh <task-dir>}"
INSTR="$TASK/instruction.md"
[ -f "$INSTR" ] || { echo "check-instruction-hygiene: OK ($TASK) [no instruction.md]"; exit 0; }

INVENTORY="$(cd "$(dirname "$0")/../.." && pwd)/ci/tool_inventory.txt"
FAILED=0

# Grader machinery a persona would never say. Word-boundary, case-insensitive.
while IFS= read -r pat; do
  [ -z "$pat" ] && continue
  if grep -qiE "$pat" "$INSTR"; then
    echo "FAIL $INSTR: leaks grader/harness reference matching /$pat/. The instruction must read as a natural persona request, not a description of the rig."
    FAILED=1
  fi
done <<'PATTERNS'
\breward\.toml\b
\brewardkit\b
\benabled_tools\b
\bmcp_servers\b
\boracle\b
\bnop\b
\bfinal_answer\.txt\b
\btask\.toml\b
\btest\.sh\b
\bMCP\b
\bturing-mcpatlas\b
\bharbor\b
PATTERNS

# No sandbox path leaks. The agent must discover where the data lives; naming
# /data/... or /logs/... in the prompt hands it the layout it is supposed to
# work out. Fixed-string match - the slashes make a word-boundary regex moot.
while IFS= read -r leak; do
  [ -z "$leak" ] && continue
  if grep -qF "$leak" "$INSTR"; then
    echo "FAIL $INSTR: references sandbox path '$leak'. The agent must discover the data layout itself - describe the job, not the path."
    FAILED=1
  fi
done <<'LEAKS'
/data/
/logs/
LEAKS

# No tool ids (exact strings, e.g. git_git_log) from the inventory.
if [ -f "$INVENTORY" ]; then
  while IFS= read -r tool; do
    case "$tool" in ''|'#'*) continue ;; esac
    # fixed-string, but require a non-word char or edge on both sides so a tool
    # id that is a prefix of a longer word does not fire.
    if grep -qF "$tool" "$INSTR" && grep -qE "(^|[^A-Za-z0-9_-])$(printf '%s' "$tool" | sed 's/[][\.*^$/]/\\&/g')([^A-Za-z0-9_-]|$)" "$INSTR"; then
      echo "FAIL $INSTR: names tool '$tool'. The agent must work out the toolchain itself - describe the job, not the tool."
      FAILED=1
    fi
  done < "$INVENTORY"
fi

# No server names from task.toml's mcp_servers blocks (word-boundary so "git"
# in prose does not fire, but the server name as a standalone word does).
if [ -f "$TASK/task.toml" ]; then
  while IFS= read -r server; do
    [ -z "$server" ] && continue
    esc=$(printf '%s' "$server" | sed 's/[][\.*^$/]/\\&/g')
    if grep -qiE "(^|[^A-Za-z0-9_-])${esc}([^A-Za-z0-9_-]|$)" "$INSTR"; then
      echo "FAIL $INSTR: names server '$server'. Describe the data, not the server."
      FAILED=1
    fi
  done < <(awk '/^\[\[environment\.mcp_servers\]\]/{inblock=1;next} /^\[\[/{inblock=0} inblock && /^name[ \t]*=/{gsub(/"/,"");sub(/^name[ \t]*=[ \t]*/,"");print}' "$TASK/task.toml")
fi

if [ "$FAILED" -eq 1 ]; then
  echo "check-instruction-hygiene: problem(s) found"
  exit 1
fi
echo "check-instruction-hygiene: OK ($TASK)"
