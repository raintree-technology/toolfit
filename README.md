# ToolFit

Find tools and agent capabilities that fit your work.

ToolFit reads limited local project metadata and matches it against capability catalogs.
Give it a task to narrow the recommendations. Relevant capabilities already declared,
configured, or present appear before new additions.

**Status: experimental alpha.** Recommendations are discovery leads. They do not
establish compatibility, safety, or a reason to install something.

## Try it locally

Requires Python 3.11 or later. ToolFit has no third-party runtime dependencies.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/toolfit . --source builtin --offline --task "improve release checks"
```

From a source checkout, use `PYTHONPATH=src python3 -m toolfit` instead of the
installed command. The old `ate-scan` command remains an alias. The Python package
is now `toolfit`; update imports and module invocations that used the old name.
The Python distribution is `raintree-toolfit` because an unrelated project owns
the `toolfit` name on PyPI.
The GitHub repository is [raintree-technology/toolfit](https://github.com/raintree-technology/toolfit).

## Choose the sources

By default, ToolFit combines its maintained starter catalog, Cohere Labs ATE, and
the official MCP Registry. The first online run downloads the remote catalogs.
Project terms and task text are never sent with those requests.

```sh
# Combine the default sources.
toolfit ./project --task "improve release checks"

# Use only the official registry and built-in guidance.
toolfit ./project --source registry --source builtin --task "test browser behavior"

# Combine local catalogs, including existing ATE JSONL files.
toolfit ./project --catalog team.jsonl --catalog ate.jsonl --offline

# Read a checked-out Codex or Claude plugin marketplace.
toolfit ./project --marketplace ../plugins --source builtin --offline

# Include recognized configuration and skill directories in your home folder.
toolfit ./project --include-agent-configs --task "review code quality"

# Save a report and an optional inert MCP configuration review bundle.
toolfit ./project --offline --output report.md --review-config mcp-review.md
```

| Source | What it contributes | Limits |
| --- | --- | --- |
| `builtin` | A maintained starter catalog of developer tools and native features, with primary documentation links and review dates | Five initial entries: Python unittest, GitHub Actions, Playwright, Ruff, and Biome. This is intentionally limited coverage. |
| `ate` | Cohere Labs ATE tool-to-task matches classified as `good` | ATE is one source. Its match count is not a count of distinct tools. |
| `registry` | Active latest server records from the [official MCP Registry API](https://registry.modelcontextprotocol.io/docs), including package and transport metadata | Publisher metadata does not prove successful operation. |
| `--catalog` | Repeatable local JSONL catalogs for MCP capabilities, plugins, skills, developer tools, and native features | ToolFit validates the record shape, not the publisher's claims. |
| `--marketplace` | Plugin descriptions from a selected marketplace checkout | Listings establish discoverability, not installation. No remote plugin sources are fetched. |
| Local skills | Names and descriptions in recognized skill directories | Skill instructions are never executed. Complex YAML descriptions are skipped. |

Supplying `--catalog` or `--marketplace` replaces the default source selection.
Add explicit `--source` flags to combine them with built-in or remote sources.

`--offline` prevents all network requests. Missing remote caches are reported as
omitted sources; available sources still produce a report. `--refresh-catalog`
refreshes selected remote catalogs and cannot be combined with `--offline`.
Failed downloads do not replace complete caches. A failed refresh is reported as
an omitted source for that run; retry offline to use the previous cache.

Public caches live under `${XDG_CACHE_HOME:-$HOME/.cache}/toolfit/` as `ate.jsonl`
and `registry.jsonl`. An existing legacy ATE cache at
`ate-mcp-opportunity-scanner/onet-good.jsonl` is reused when the new ATE cache is
absent. Project metadata and task text never enter these caches.

## What a recommendation explains

- The capability type and published purpose.
- The task words and repository workflows that matched.
- Existing availability evidence, such as a dependency declaration or configured server name.
- Source links, source update dates when provided, and retrieval or review dates.
- Stated access requirements and inferred permission signals.
- Available compatibility and repository maintenance evidence.
- What still needs checking before use.

A dependency declaration does not prove installation. A configured server name
does not prove that the server is enabled. An enabled plugin key does not prove
that its runtime works. ToolFit preserves these distinctions in the report.

Matching uses lexical signals, workflow profiles, and local availability evidence.
It does not use a hosted model or an embedding service. Supplying `--task` requires
at least one task-term match. Matching remains heuristic; common terms can produce
false positives. Scores are report-local ranking values, not probabilities.

Repeated entries with the same capability kind, publisher, and name are combined
while retaining their source records. Similar names from different publishers
remain separate. A registry server and one of its individual ATE tools can remain
separate because they describe different levels of capability.

## Privacy and execution boundary

ToolFit scans only the project folders you select. It reads filenames, approved
manifest metadata, dependency names, script names, and Markdown headings.
It skips generated folders, symlinks, oversized files, and credential files.
It never executes project scripts or recommended tools.

Recognized local skill folders are `.agents/skills`, `.codex/skills`, and
`.claude/skills`. ToolFit reads a bounded prefix of `SKILL.md` and extracts only
simple frontmatter names and descriptions. It does not interpret the body.

MCP configurations contribute server names, not commands, URLs, headers, or secret
values. Plugin availability uses exact enabled keys in Codex `plugins` tables or
Claude `enabledPlugins` settings. Home-folder configuration and skill checks require
`--include-agent-configs`. Plugin cache directories are not treated as installations.

Online requests fetch public catalogs and screen public candidate GitHub metadata.
They do not contain project names, paths, dependencies, task text, or reports.
The report includes the selected project folder name and the task you supplied.
Keep sensitive text out of `--task` if you do not want it in shell history or reports.

An optional `--review-config` bundle contains MCP candidates only. Its templates
use `.review` filenames and placeholders. It does not install tools or change a
client configuration. Non-MCP recommendations never become MCP templates.

See [catalog format](docs/catalogs.md), [security boundaries](SECURITY.md),
[evaluation limits](EVALUATION.md), and [error recovery](docs/errors.md).

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

See [contribution requirements](CONTRIBUTING.md). Do not commit downloaded catalogs,
private reports, or credentials. Built-in catalog descriptions are authored here
and cite primary documentation; they are not copies of third-party dataset rows.
