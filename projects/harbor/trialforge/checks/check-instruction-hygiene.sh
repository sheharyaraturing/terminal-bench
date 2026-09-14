#!/usr/bin/env bash
# The instruction must read as a natural persona request.
#
# CONTRIBUTING.md: names no tool and no server, not once. The agent must work
# out the toolchain itself. It also must not leak grader machinery (fourth
# wall). Pure greps over instruction.md - no parsing needed. The tool inventory
# is inlined below so this check is standalone (no sidecar file, no network).
set -u

TASK="${1:?usage: check-instruction-hygiene.sh <task-dir>}"
INSTR="$TASK/instruction.md"
[ -f "$INSTR" ] || { echo "check-instruction-hygiene: OK ($TASK) [no instruction.md]"; exit 0; }

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

# Sandbox paths in the instruction. We ALLOW a sandbox path when it aligns
# with the task's Dockerfile - the agent may be told where data lives, provided
# the instruction and the container agree. Two cases fail:
#   - /logs/... : the harness/judge output area, never the task's data; naming
#     it leaks grader machinery.
#   - any other path the Dockerfile does not create: a path that does not
#     exist in the container misleads the agent, so the instruction and Dockerfile
#     must agree.
# Every absolute path token in the instruction is checked against the Dockerfile
# - no hardcoded data roots. URLs are stripped first and a leading non-word
# boundary excludes fractions like "3/4", so only real file paths are examined.
# "Aligned" means the path equals, is an ancestor of, or is a descendant of a
# path the Dockerfile materializes (COPY dest, RUN mkdir/cp/sqlite, WORKDIR).
DOCKER="$TASK/environment/Dockerfile"
DOCKER_PATHS=""
[ -f "$DOCKER" ] && DOCKER_PATHS=$(grep -v '^FROM' "$DOCKER" | grep -oE '/[A-Za-z0-9_./-]+' | sort -u)
# strip URLs, then extract absolute path tokens with a leading non-word
# boundary (excludes fractions). Strip trailing sentence punctuation.
instr_no_url=$(sed -E 's#[a-zA-Z][a-zA-Z0-9+.-]*://[^[:space:]]+##g' "$INSTR")
paths_in_instr=$(grep -oE '(^|[^A-Za-z0-9_])/[A-Za-z0-9_./-]+' <<<"$instr_no_url" | sed 's/^[^/]*//' | sed 's/\.$//' | sort -u)
while IFS= read -r p; do
  [ -z "$p" ] && continue
  case "$p" in
    /logs/*)
      echo "FAIL $INSTR: references sandbox path '$p'. /logs/ is the harness/judge area, never the task's data - naming it leaks grader machinery."
      FAILED=1
      ;;
    *)
      pp="${p%/}"
      aligned=0
      while IFS= read -r d; do
        [ -z "$d" ] && continue
        dd="${d%/}"
        if [ "$pp" = "$dd" ] || case "$dd" in "$pp"/*) :;; *) false;; esac || case "$pp" in "$dd"/*) :;; *) false;; esac; then
          aligned=1
          break
        fi
      done <<<"$DOCKER_PATHS"
      if [ "$aligned" -eq 0 ]; then
        echo "FAIL $INSTR: references sandbox path '$p', which the Dockerfile does not create. The instruction and the Dockerfile must agree on the data layout - describe the job with a path the container actually provides."
        FAILED=1
      fi
      ;;
  esac
done <<<"$paths_in_instr"

# No tool ids (exact strings, e.g. git_git_log) from the inventory. The full
# 210-tool surface is inlined below; comment/blank lines are skipped.
while IFS= read -r tool; do
  case "$tool" in ''|'#'*) continue ;; esac
  # fixed-string, but require a non-word char or edge on both sides so a tool
  # id that is a prefix of a longer word does not fire.
  if grep -qF "$tool" "$INSTR" && grep -qE "(^|[^A-Za-z0-9_-])$(printf '%s' "$tool" | sed 's/[][\.*^$/]/\\&/g')([^A-Za-z0-9_-]|$)" "$INSTR"; then
    echo "FAIL $INSTR: names tool '$tool'. The agent must work out the toolchain itself - describe the job, not the tool."
    FAILED=1
  fi
done <<'INVENTORY'
# trialforge tool inventory - the complete tool surface of the environment image.
#
# Image : us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.1
# Digest: sha256:6798daea4ef7a17ade2c157636dce1517b5cd3c8744ca3ad93ca611db9f45215
# Source: POST /list-tools against the image's sandbox REST API on :1984.
# Shape : 19 servers, 210 tools.
#
# Names are EXACTLY what the sandbox's composite FastMCP client reports, already
# namespaced {server}_{tool}. Some double-prefix (git_git_log, whois_whois_domain,
# wikipedia_wikipedia_get_summary). The harness filters client-side with
#     tools.filter(t => enabledTools.includes(t.name))
# which is a SILENT intersection: a typo'd name simply never reaches the model and
# nothing anywhere reports it. That is why CI checks this list offline on every PR.
#
# Regenerate only when the image tag changes, and update the digest above with it.
# Lines starting with '#' and blank lines are ignored by the checker.

# --- arxiv (14) ---
arxiv_check_alerts
arxiv_citation_graph
arxiv_download_paper
arxiv_export_citations
arxiv_get_abstract
arxiv_get_paper_latex
arxiv_get_paper_latex_section
arxiv_list_paper_latex_sections
arxiv_list_papers
arxiv_read_paper
arxiv_reindex
arxiv_search_papers
arxiv_semantic_search
arxiv_watch_topic

# --- calculator (1) ---
calculator_calculate

# --- cli-mcp-server (2) ---
cli-mcp-server_run_command
cli-mcp-server_show_security_rules

# --- context7 (2) ---
context7_query-docs
context7_resolve-library-id

# --- crossref (18) ---
crossref_get_funder
crossref_get_funder_works
crossref_get_journal
crossref_get_journal_works
crossref_get_member
crossref_get_member_works
crossref_get_prefix
crossref_get_type
crossref_get_work
crossref_get_work_quality
crossref_get_work_references
crossref_list_licenses
crossref_list_types
crossref_ping
crossref_search_funders
crossref_search_journals
crossref_search_members
crossref_search_works

# --- ddg-search (2) ---
ddg-search_fetch_content
ddg-search_search

# --- desktop-commander (26) ---
desktop-commander_create_directory
desktop-commander_edit_block
desktop-commander_force_terminate
desktop-commander_get_config
desktop-commander_get_file_info
desktop-commander_get_more_search_results
desktop-commander_get_prompts
desktop-commander_get_recent_tool_calls
desktop-commander_get_usage_stats
desktop-commander_give_feedback_to_desktop_commander
desktop-commander_interact_with_process
desktop-commander_kill_process
desktop-commander_list_directory
desktop-commander_list_processes
desktop-commander_list_searches
desktop-commander_list_sessions
desktop-commander_move_file
desktop-commander_read_file
desktop-commander_read_multiple_files
desktop-commander_read_process_output
desktop-commander_set_config_value
desktop-commander_start_process
desktop-commander_start_search
desktop-commander_stop_search
desktop-commander_write_file
desktop-commander_write_pdf

# --- fetch (1) ---
fetch_fetch

# --- filesystem (14) ---
filesystem_create_directory
filesystem_directory_tree
filesystem_edit_file
filesystem_get_file_info
filesystem_list_allowed_directories
filesystem_list_directory
filesystem_list_directory_with_sizes
filesystem_move_file
filesystem_read_file
filesystem_read_media_file
filesystem_read_multiple_files
filesystem_read_text_file
filesystem_search_files
filesystem_write_file

# --- git (12) ---
git_git_add
git_git_branch
git_git_checkout
git_git_commit
git_git_create_branch
git_git_diff
git_git_diff_staged
git_git_diff_unstaged
git_git_log
git_git_reset
git_git_show
git_git_status

# --- mcp-code-executor (9) ---
mcp-code-executor_append_to_code_file
mcp-code-executor_check_installed_packages
mcp-code-executor_configure_environment
mcp-code-executor_execute_code
mcp-code-executor_execute_code_file
mcp-code-executor_get_environment_config
mcp-code-executor_initialize_code_file
mcp-code-executor_install_dependencies
mcp-code-executor_read_code_file

# --- mcp-server-code-runner (1) ---
mcp-server-code-runner_run-code

# --- memory (9) ---
memory_add_observations
memory_create_entities
memory_create_relations
memory_delete_entities
memory_delete_observations
memory_delete_relations
memory_open_nodes
memory_read_graph
memory_search_nodes

# --- open-library (6) ---
open-library_get_author_info
open-library_get_author_photo
open-library_get_authors_by_name
open-library_get_book_by_id
open-library_get_book_by_title
open-library_get_book_cover

# --- paper-search (57) ---
paper-search_download_arxiv
paper-search_download_base
paper-search_download_biorxiv
paper-search_download_citeseerx
paper-search_download_crossref
paper-search_download_dblp
paper-search_download_doaj
paper-search_download_hal
paper-search_download_iacr
paper-search_download_medrxiv
paper-search_download_openaire
paper-search_download_openalex
paper-search_download_pubmed
paper-search_download_scihub
paper-search_download_semantic
paper-search_download_ssrn
paper-search_download_with_fallback
paper-search_download_zenodo
paper-search_get_crossref_paper_by_doi
paper-search_read_arxiv_paper
paper-search_read_base_paper
paper-search_read_biorxiv_paper
paper-search_read_citeseerx_paper
paper-search_read_crossref_paper
paper-search_read_dblp_paper
paper-search_read_doaj_paper
paper-search_read_hal_paper
paper-search_read_iacr_paper
paper-search_read_medrxiv_paper
paper-search_read_openaire_paper
paper-search_read_openalex_paper
paper-search_read_pubmed_paper
paper-search_read_semantic_paper
paper-search_read_ssrn_paper
paper-search_read_zenodo_paper
paper-search_search_arxiv
paper-search_search_base
paper-search_search_biorxiv
paper-search_search_citeseerx
paper-search_search_core
paper-search_search_crossref
paper-search_search_dblp
paper-search_search_doaj
paper-search_search_europepmc
paper-search_search_google_scholar
paper-search_search_hal
paper-search_search_iacr
paper-search_search_medrxiv
paper-search_search_openaire
paper-search_search_openalex
paper-search_search_papers
paper-search_search_pmc
paper-search_search_pubmed
paper-search_search_semantic
paper-search_search_ssrn
paper-search_search_unpaywall
paper-search_search_zenodo

# --- sqlite (8) ---
sqlite_create_record
sqlite_db_info
sqlite_delete_records
sqlite_get_table_schema
sqlite_list_tables
sqlite_query
sqlite_read_records
sqlite_update_records

# --- time (2) ---
time_convert_time
time_get_current_time

# --- whois (4) ---
whois_whois_as
whois_whois_domain
whois_whois_ip
whois_whois_tld

# --- wikipedia (22) ---
wikipedia_extract_key_facts
wikipedia_get_article
wikipedia_get_coordinates
wikipedia_get_links
wikipedia_get_related_topics
wikipedia_get_sections
wikipedia_get_summary
wikipedia_search_wikipedia
wikipedia_summarize_article_for_query
wikipedia_summarize_article_section
wikipedia_test_wikipedia_connectivity
wikipedia_wikipedia_extract_key_facts
wikipedia_wikipedia_get_article
wikipedia_wikipedia_get_coordinates
wikipedia_wikipedia_get_links
wikipedia_wikipedia_get_related_topics
wikipedia_wikipedia_get_sections
wikipedia_wikipedia_get_summary
wikipedia_wikipedia_search_wikipedia
wikipedia_wikipedia_summarize_article_for_query
wikipedia_wikipedia_summarize_article_section
wikipedia_wikipedia_test_wikipedia_connectivity
INVENTORY

# No server names from task.toml's mcp_servers blocks (word-boundary so a
# substring of a longer word does not fire, but the server name as a standalone
# token does).
#
# Two classes, by how prose-like the name is:
#   - Distinctive names (every server EXCEPT the few common English words
#     below): never appear in ordinary prose, so any standalone match is a real
#     leak -> fire on word-boundary match alone.
#   - English-word names (time, memory, fetch, git, calculator): common words,
#     so a bare match is usually innocent ("at the time", "keep in memory",
#     "fetch the records"). Fire ONLY when the name shares a line with a
#     tool/server-context word (server, tool, mcp, plugin, api, endpoint,
#     integration, connect) - i.e. how a real leak reads ("use the time
#     server"). This still catches leaks the old full-skip would have missed,
#     while ignoring prose. The grader-machinery patterns above already catch
#     "MCP"/"harbor"/"turing-mcpatlas" outright; the tool-id grep above still
#     catches an explicit tool from any of these servers (e.g.
#     time_get_current_time).
if [ -f "$TASK/task.toml" ]; then
  CTX='(server|tool|mcp|plugin|api|endpoint|integration|connect)'
  while IFS= read -r server; do
    [ -z "$server" ] && continue
    esc=$(printf '%s' "$server" | sed 's#[][\\.^$*+?(){}|/-]#\\&#g')
    pat="(^|[^A-Za-z0-9_-])${esc}([^A-Za-z0-9_-]|$)"
    hits=$(grep -niE "$pat" "$INSTR")
    [ -z "$hits" ] && continue
    case "$server" in time|memory|fetch|git|calculator)
      # require a context word on one of the matching lines
      echo "$hits" | grep -qiE "$CTX" || continue
    ;; esac
    echo "FAIL $INSTR: names server '$server'. Describe the data, not the server."
    FAILED=1
  done < <(awk '/^\[\[environment\.mcp_servers\]\]/{inblock=1;next} /^\[\[/{inblock=0} inblock && /^name[ \t]*=/{gsub(/"/,"");sub(/^name[ \t]*=[ \t]*/,"");print}' "$TASK/task.toml")
fi

if [ "$FAILED" -eq 1 ]; then
  echo "check-instruction-hygiene: problem(s) found"
  exit 1
fi
echo "check-instruction-hygiene: OK ($TASK)"
