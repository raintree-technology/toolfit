# Add a capability catalog

Use a local JSONL file to add capabilities from another catalog. Each nonblank line
contains one JSON object. Pass `--catalog` once per file.

```json
{"id":"example:release-checks","name":"Release checks","kind":"skill","description":"Review release artifacts, package metadata, and continuous integration checks.","task_text":"release testing packaging","source_name":"Example team catalog","source_url":"https://example.com/release-checks","source_updated_at":"2026-09-01","source_checked_at":"2026-09-08","access":"Read repository metadata and build artifacts.","requirements":"A compatible agent and access to release artifacts."}
```

| Field | Meaning |
| --- | --- |
| `id` | Source-specific capability identifier. |
| `name`, `description` | Display name and purpose. Descriptions under 20 characters are excluded from ranking. |
| `kind` | `mcp`, `plugin`, `skill`, `tool`, or `native`. Defaults to `mcp` for ATE compatibility. |
| `task_text` | Additional task vocabulary used in matching. |
| `project_signals` | Optional applicability terms. At least one must occur in project or task metadata. |
| `source_name`, `source_url` | Attribution label and HTTPS documentation or catalog link. |
| `source_updated_at` | Publisher-provided update date, if known. |
| `source_checked_at` | Date the metadata was retrieved or reviewed, if known. |
| `github_url` | Public GitHub repository URL for optional online screening. |
| `package_names` | Exact dependency names, separated by JSON-escaped newlines. Used as declaration evidence. |
| `plugin_key` | Exact enabled configuration key, such as `checks@example`. |
| `transports` | Explicit MCP transport names, if documented. |
| `access`, `requirements` | Stated access needs and setup requirements. Missing information remains unknown. |

Fields use scalar strings. Unknown fields are discarded, including executable
configuration. Catalog rows cannot assert local availability. ToolFit derives it
from the selected project and optional recognized home configuration.

ATE JSONL rows using `tool_name`, `tool_description`, `server_name`, `mcp_id`,
`task_text`, and repository metadata remain supported. The importer adds ATE
attribution. ATE cache write dates indicate retrieval, not upstream publication.

Files are limited to 100,000 lines and 256,000 characters per line. Supported
metadata files are limited to 256,000 bytes. Symlink catalogs are rejected.
The registry adapter caps page count and response size and refuses redirects.
A complete download replaces its cache atomically.

## Plugin marketplaces

Pass a checkout directory containing either `.agents/plugins/marketplace.json`
(Codex) or `.claude-plugin/marketplace.json` (Claude). Relative local plugin sources
can supply descriptions from `.codex-plugin/plugin.json` or
`.claude-plugin/plugin.json`. Local source paths must stay within the selected
checkout and cannot traverse symlinks. Remote source references are not fetched;
only descriptions already present in the marketplace entry can contribute.

A marketplace listing is a candidate, not proof of installation. An exact plugin
key in an explicitly enabled local configuration adds availability evidence.
