# Connect a reviewed MCP server

Use this guide only after you review a candidate's source, permissions, data destinations, maintenance, and installation instructions. The scanner does not verify that a server works with your agent.

Keep credentials in environment variables or the agent's supported credential store. Do not commit secrets to a project configuration. Obtain the server command, arguments, and authentication instructions from the reviewed server's publisher before you begin.

Generate an inert starting point with `toolfit PROJECT --review-config mcp-configuration-review.md`. The bundle uses `.review` filenames, placeholder commands, and placeholder server-side read-only arguments. It does not modify a client configuration. Treat the bundle as a review worksheet, not as an installation file.

No common client setting can turn every unknown MCP server into a read-only server. Verify a server-specific read-only mode and expose only reviewed read operations before activation.

## Codex

Codex supports local standard input/output (STDIO) servers and remote Streamable HTTP servers. The ChatGPT desktop app, Codex CLI, and Codex IDE extension share host configuration.

1. Add the reviewed local STDIO server with the publisher's command and arguments.

   ```shell
   codex mcp add <server-name> -- <server-command> <arguments>
   ```

2. Confirm that Codex lists the server.

   ```shell
   codex mcp list
   ```

   Registration succeeds when `<server-name>` appears in the list. If it does not appear, follow the troubleshooting guidance in the official documentation below.

Codex stores user configuration in `~/.codex/config.toml`. Trusted projects can use `.codex/config.toml`. Use environment-variable references for credentials. Keep a reviewed server disabled during configuration review, restrict its enabled tools, and use prompt-based approval for every tool until you establish trust.

Follow the [official Codex MCP documentation](https://developers.openai.com/codex/mcp) for remote servers, OAuth, tool allowlists, and approval controls.

Remove the server later with `codex mcp remove <server-name>`, then confirm its absence with `codex mcp list`.

## Claude Code

1. Add the reviewed local STDIO server with the publisher's command and arguments.

   ```shell
   claude mcp add <server-name> -- <server-command> <arguments>
   ```

2. Confirm that Claude Code lists the server.

   ```shell
   claude mcp list
   ```

   Registration succeeds when `<server-name>` appears in the list. If it does not appear, follow the troubleshooting guidance in the official documentation below.

Claude Code supports local, project, and user scopes. Project-scoped servers use `.mcp.json` and require project approval. That approval protects the configuration boundary; it does not prove that a server or tool is read-only. Keep machine-specific credentials outside the shared file.

Follow the [official Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp) for scopes, remote transports, OAuth, and configuration import.

Remove the server later with `claude mcp remove <server-name> -s <scope>`. Use the same `local`, `project`, or `user` scope that you selected when adding it, then confirm its absence with `claude mcp list`.

## Cursor

Cursor supports one-click MCP installation and custom `mcp.json` configuration.

1. Use Cursor's MCP interface when the reviewed server provides an official installation link. Otherwise, add the publisher's documented command or remote URL to `mcp.json`.
2. Open Cursor's MCP settings and confirm that `<server-name>` appears as enabled. If it does not appear, follow the troubleshooting guidance in the official documentation below.

Follow the [official Cursor MCP documentation](https://cursor.com/docs/mcp) for supported transports, configuration locations, and authentication.

Review Cursor's tool allowlist and approval controls before enabling a server. These controls reduce exposure but do not replace a verified server-side read-only mode.

Remove the server later from the same MCP settings interface or `mcp.json` file, then confirm that it no longer appears as enabled.

## Grok Build

1. Add the reviewed local STDIO server with the publisher's command and arguments.

   ```shell
   grok mcp add <server-name> -- <server-command> <arguments>
   ```

2. List the configured MCP servers.

   ```shell
   grok mcp list
   ```

   Registration succeeds when `<server-name>` appears in the list.

3. Diagnose the server if it does not appear or start.

   ```shell
   grok mcp doctor
   ```

Grok Build stores user settings in `~/.grok/config.toml` and project MCP settings in `.grok/config.toml`. It can also load compatible Claude and Cursor MCP configurations. Keep the server disabled during review and use environment-variable expansion instead of literal credentials.

Follow the [official Grok Build MCP documentation](https://docs.x.ai/build/features/mcp-servers) for scopes, configuration precedence, remote servers, and troubleshooting.

Remove the server later with `grok mcp remove <server-name>`, then run `grok mcp list` to confirm its absence.
