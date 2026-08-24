#!/usr/bin/env bash
# Every uvx MCP server must pin mcp<2 and a version; npx servers pin @version.
#
# mcp 2.0.0 is a breaking release of the Python SDK: pinning only the *server*
# version is not enough - the transitive SDK floats to 2.0.0 and the server
# crashes on import, then silently fails to register (docs/ENVIRONMENT.md).
#
# Line-oriented scan of task.toml, not a TOML parse - the structure is flat
# enough that awk on the [[environment.mcp_servers]] blocks is clearer than a
# parser. Failures are collected via a temp file because the block loop runs in
# a pipeline (subshell) and cannot set a parent-shell flag.
set -u

TASK="${1:?usage: check-mcp-uvx-pin.sh <task-dir>}"
TOML="$TASK/task.toml"
[ -f "$TOML" ] || { echo "FATAL: $TOML missing"; exit 2; }

FAILS=$(mktemp)
: > "$FAILS"

# Emit one record per server block: NAME <tab> the block with newlines as \x01.
awk '
  /^\[\[environment\.mcp_servers\]\]/ { if (name != "") emit(); inblock=1; name=""; buf=""; next }
  /^\[\[/ && inblock { inblock=0; if (name != "") emit(); name="" }
  inblock {
    buf = buf $0 "\x01"
    if ($0 ~ /^name[ \t]*=/) { n=$0; gsub(/"/, "", n); sub(/^name[ \t]*=[ \t]*/, "", n); name=n }
  }
  END { if (inblock && name != "") emit() }
  function emit() { printf "%s\t%s\n", name, buf }
' "$TOML" | while IFS=$'\t' read -r name block; do
  [ -z "$name" ] && continue
  # \x01 back to real newlines for grep
  body=$(printf '%s' "$block" | tr '\001' '\n')

  if printf '%s\n' "$body" | grep -q '^command[ \t]*=[ \t]*"uvx"'; then
    if ! printf '%s\n' "$body" | grep -q 'mcp<2'; then
      echo "FAIL $TOML: server '$name' (uvx) is missing \`--with mcp<2\`. The mcp SDK floats to 2.0.0, the server crashes on import, and it silently fails to register." >> "$FAILS"
    fi
    if ! printf '%s\n' "$body" | grep -Eq '(==[0-9]|--from[ \t]*"[^"]*==[0-9])'; then
      echo "FAIL $TOML: server '$name' (uvx) has no pinned package version (pkg==x.y.z or --from pkg==x.y.z). An unpinned server can change under the eval." >> "$FAILS"
    fi
  elif printf '%s\n' "$body" | grep -q '^command[ \t]*=[ \t]*"npx"'; then
    printf '%s\n' "$body" | grep '^args' | tr ',' '\n' | while IFS= read -r arg; do
      case "$arg" in -*|/*|./*) continue ;; esac
      clean=$(printf '%s' "$arg" | tr -d '",[]' | xargs)
      [ -z "$clean" ] && continue
      if printf '%s' "$clean" | grep -Eq '^@?[A-Za-z][A-Za-z0-9._-]*(/[A-Za-z0-9._-]+)?$'; then
        if ! printf '%s' "$clean" | grep -Eq '@[0-9]'; then
          echo "FAIL $TOML: server '$name' (npx) package '$clean' is not version-pinned. Use @scope/pkg@x.y.z so the server cannot drift." >> "$FAILS"
        fi
      fi
    done
  fi
done

if [ -s "$FAILS" ]; then
  cat "$FAILS"
  N=$(wc -l < "$FAILS" | tr -d ' ')
  rm -f "$FAILS"
  echo "check-mcp-uvx-pin: $N problem(s)"
  exit 1
fi
rm -f "$FAILS"
echo "check-mcp-uvx-pin: OK ($TASK)"
