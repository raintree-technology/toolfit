# Security

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Send a report through [GitHub's private vulnerability reporting form](https://github.com/raintree-technology/toolfit/security/advisories/new).

Include the affected version, reproduction steps, impact, and any suggested remediation. Do not include credentials or private project content.

## Trust model

The scanner treats project paths, filenames, manifests, catalog rows, repository documentation, repository metadata, and tool descriptions as untrusted data.

The scanner must:

- Read only the user-selected project folders.
- Read recognized agent configurations outside those folders only after the user passes `--include-agent-configs`.
- Reject filesystem-root scans.
- Skip symlinks, credential files, environment files, private keys, generated folders, and oversized files.
- Extract keys only from MCP and agent JSON configurations.
- Extract MCP server table names only from recognized JSON and TOML configurations; do not retain their commands, arguments, URLs, environment values, or headers.
- Avoid executing project files, manifest scripts, MCP servers, or downloaded code.
- Write configuration suggestions only to a user-selected review bundle. Use `.review` filenames, placeholder commands, and placeholder server-side read-only arguments so the bundle is not a live client configuration.
- Avoid sending project content, project terms, paths, or scanner reports to network services.
- Send only public ATE identifiers and public repository identifiers when resolving candidate metadata and transport evidence.
- Read at most 256 KB from each supported public repository metadata file. Do not clone or execute candidate code.
- Keep scanner reports local unless the user publishes them.
- Retain public catalog data only in the documented user cache until the user refreshes or deletes it.

## Candidate screening

Risk labels identify words associated with destructive or state-changing actions. Repository screens check limited public metadata such as archive status, detected license, and last update. Neither mechanism is a security audit.

Compatibility states identify only explicit transports named in public ATE metadata, repository documentation, or root package metadata and compare them with documented client transports. They do not establish successful installation, authentication, protocol behavior, or tool safety. Permission signals are also keyword evidence, not observed runtime permissions.

The generated review bundle is inert by default. Codex and Grok examples also set the server to disabled. Claude Code and Cursor examples rely on the `.review` filename because their shared MCP configuration format does not provide a universal server-side read-only guarantee. A reviewer must confirm a real server-specific read-only mode, remove write-capable tools, and test the result before activation.

Review a candidate's source code, dependency chain, requested permissions, authentication, data destinations, destructive operations, and maintenance before installation.

## ToolFit catalogs and local availability

The official MCP Registry adapter sends only pagination and version-selection
parameters to its fixed HTTPS endpoint. It refuses redirects, caps response and
page sizes, and replaces caches only after a complete download. Task text and
project metadata never enter these requests.

Local catalogs are bounded JSONL data. Unknown fields and executable
configuration are discarded. Catalogs cannot assert that a capability is
installed. Plugin marketplace metadata stays within the selected checkout;
escaping paths and symlinks are rejected. ToolFit never fetches remote plugin
sources or executes plugin hooks.

Local skills contribute simple names and descriptions from a bounded frontmatter
prefix. Dependency names establish declarations only. Explicitly enabled plugin
keys establish configuration only. Neither establishes working software.
Home configuration and skill discovery require `--include-agent-configs`.

Task text appears in local reports and can remain in shell history. Reports
contain source coverage and mark unavailable catalogs. Missing evidence must not
be represented as a successful compatibility or security check.
