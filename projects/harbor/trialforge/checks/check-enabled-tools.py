#!/usr/bin/env python3
"""enabled_tools against the shipped tool inventory.

The harness filters client-side:  tools.filter(t => enabledTools.includes(t.name))
A misspelled name is a SILENT set intersection - the tool simply never reaches
the model, the agent underperforms for no visible reason, and nothing in Harbor,
the harness, or the sandbox says a word.
"""
from __future__ import annotations

from _lib import (declared_servers, enabled_tools, load_toml, make_err, report,
                  task_arg, tool_prefix)

# Offline copy of POST /list-tools for the pinned image (no network, no sidecar
# file). Regenerate only when the image tag changes; update digest with it.
#
# Image : us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.1
# Digest: sha256:6798daea4ef7a17ade2c157636dce1517b5cd3c8744ca3ad93ca611db9f45215
# Shape : 19 servers, 210 tools.
#
# Names are EXACTLY what the sandbox's composite FastMCP client reports, already
# namespaced {server}_{tool}. Some double-prefix (git_git_log, whois_whois_domain,
# wikipedia_wikipedia_get_summary).
_TOOL_INVENTORY_RAW = """
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
"""

TOOL_INVENTORY: frozenset[str] = frozenset(
    line.strip()
    for line in _TOOL_INVENTORY_RAW.splitlines()
    if line.strip() and not line.strip().startswith("#")
)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    tools = enabled_tools(task_cfg)
    if tools is None:
        err(f"{task}/task.toml: [metadata].enabled_tools is required and must be a "
            "non-empty array of strings. Harbor itself ignores [metadata]; the wrapper "
            "reads this list and passes it to the harness as enabledTools. Without it "
            "the agent is handed the entire 210-tool surface.")
        return report("check-enabled-tools", task, errors, notes)

    # Duplicate entries are reported by check-mcp-config (which owns the
    # enabled_tools <-> declared-server cross-reference); not repeated here.

    for t in tools:
        if t not in TOOL_INVENTORY:
            # Point at the double-prefix trap by name where we can.
            near = sorted(n for n in TOOL_INVENTORY if t in n or n.endswith("_" + t))
            hint = f" Did you mean: {near[:3]}?" if near else ""
            err(f"{task}/task.toml: enabled_tools entry {t!r} is not in the image's "
                f"tool inventory.{hint}")

    servers = sorted({tool_prefix(t) for t in tools})
    notes.append(f"enabled_tools spans {len(servers)} server prefixes: {', '.join(servers)}")

    # Declared MCP servers are informational (the wrapper does not use
    # mcp_servers - tools come via enabledTools), but a task whose allowlist
    # names a server it never declares is almost certainly a copy-paste error
    # worth surfacing as a note, not a hard fail.
    declared = declared_servers(task_cfg)
    if declared:
        orphan = sorted(set(servers) - declared)
        if orphan:
            notes.append(f"enabled_tools references servers not declared in "
                         f"[[environment.mcp_servers]]: {orphan}")

    return report("check-enabled-tools", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
