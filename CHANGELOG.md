# Changelog

## 0.2.0 — 2026-09-08

- Rename the product and primary command to ToolFit; keep `ate-scan` as an alias.
- Publish the Python distribution as `raintree-toolfit` because the `toolfit`
  name belongs to an unrelated project on PyPI.
- Add task-aware ranking and recommend relevant existing capabilities first.
- Combine ATE, the official MCP Registry, a built-in catalog, local catalogs, and plugin marketplaces.
- Detect declared dependencies, configured plugins, and local skill metadata.
- Report source dates, availability evidence, requirements, and remaining checks.
- Restrict MCP configuration templates to MCP candidates.

## 0.1.3 — 2026-09-04

- Verify explicit MCP transports from each candidate repository's public README and root package metadata.

## 0.1.2 — 2026-09-04

- Detect concrete repository workflows and include workflow fit in candidate ranking.
- Report bounded client-transport compatibility, maintenance state, permission signals, and security-review priority.
- Add `--review-config` for inert Codex, Claude Code, Cursor, and Grok Build configuration templates.
- Keep one JSONL catalog path and one reusable client-template set per repository.

## 0.1.1 — 2026-09-04

- Define MCP tools and MCP servers consistently.
- Make installation and agent-connection procedures executable and verifiable.
- Replace unsupported performance and relevance claims with bounded evidence.
- Document local report and cache retention, network recipients, and deletion.
- Add stable error codes with recovery actions for command-line failures.

## 0.1.0 — 2026-09-04

- Scan user-selected project metadata without uploading project content.
- Read MCP and agent configuration keys without reading their values, with explicit opt-in for configurations outside selected projects.
- Download matching ATE rows from the official publisher service instead of redistributing them.
- Rank candidates by project signals and opportunity classes.
- Label state-changing and destructive action signals.
- Screen resolved GitHub repositories for archive, license, and maintenance warnings.
- Document setup for Codex, Claude Code, Cursor, and Grok Build.
