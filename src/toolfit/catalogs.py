"""Bounded catalog adapters. Catalog content is data, never executable configuration."""
from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .core import MAX_CATALOG_ROWS, MAX_FILE_BYTES, USER_AGENT

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
KINDS = {"mcp", "plugin", "skill", "tool", "native"}


def normalize(row: object, source: str = "Local catalog") -> dict[str, str]:
    if not isinstance(row, dict):
        raise ValueError("catalog rows must be objects")
    # Keep only documented scalar fields; commands, credentials and configuration are discarded.
    fields = {
        "mcp_id", "tool_name", "server_name", "tool_description", "task_text", "occupation_title",
        "github_url", "github_archived", "github_pushed_at", "github_stargazers_count",
        "kind", "source_name", "source_url", "source_updated_at", "source_checked_at",
        "capability_id", "plugin_key", "package_names", "transports", "access", "requirements", "project_signals",
    }
    result = {}
    for key in fields:
        value = row.get(key)
        if value is not None:
            if not isinstance(value, (str, int, float, bool)) or len(str(value)) > 8_000:
                raise ValueError(f"invalid catalog field: {key}")
            result[key] = str(value)
    for public, internal in (("name", "tool_name"), ("description", "tool_description"), ("id", "capability_id")):
        if public in row:
            if not isinstance(row[public], str) or len(row[public]) > 8_000:
                raise ValueError(f"invalid catalog field: {public}")
            result[internal] = row[public]
    result.setdefault("kind", "mcp")
    if result["kind"] not in KINDS:
        raise ValueError("kind must be mcp, plugin, skill, tool, or native")
    result.setdefault("source_name", "Cohere Labs ATE" if "mcp_id" in result else source)
    result.setdefault("source_url", "https://huggingface.co/datasets/CohereLabs/ATE" if "mcp_id" in result else "")
    result.setdefault("server_name", result.get("tool_name", ""))
    return result


def read_catalog(path: Path):
    if path.is_symlink():
        raise ValueError("catalog symlinks are not supported")
    with path.open(encoding="utf-8") as handle:
        for count in range(MAX_CATALOG_ROWS + 1):
            line = handle.readline(MAX_FILE_BYTES + 1)
            if not line:
                return
            if count == MAX_CATALOG_ROWS or len(line) > MAX_FILE_BYTES:
                raise ValueError("catalog exceeds row or line size limit")
            if line.strip():
                yield normalize(json.loads(line))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("catalog redirects are not allowed")


def registry_page(cursor: str = "") -> dict:
    query = {"limit": 100, "version": "latest"}
    if cursor:
        query["cursor"] = cursor
    request = urllib.request.Request(
        REGISTRY_URL + "?" + urllib.parse.urlencode(query),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        payload = response.read(10_000_001)
    if len(payload) > 10_000_000:
        raise ValueError("registry page exceeds size limit")
    page = json.loads(payload)
    if not isinstance(page, dict) or not isinstance(page.get("servers"), list):
        raise ValueError("invalid registry page")
    return page


def registry_rows(page: dict, checked_at: str):
    for entry in page["servers"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("server"), dict):
            raise ValueError("invalid registry entry")
        server = entry["server"]
        official = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
        if official.get("status", "active") != "active" or official.get("isLatest") is False:
            continue
        transports, packages = set(), []
        for package in server.get("packages", []):
            if package.get("identifier"):
                packages.append(str(package["identifier"]))
            transport = package.get("transport", {}).get("type")
            if transport:
                transports.add(str(transport))
        for remote in server.get("remotes", []):
            if remote.get("type"):
                transports.add(str(remote["type"]))
        name = server.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("registry server is missing a name")
        yield normalize({
            "id": "registry:" + name, "name": name, "kind": "mcp",
            "description": server.get("description", ""),
            "github_url": server.get("repository", {}).get("url", ""),
            "source_name": "Official MCP Registry", "source_url": REGISTRY_URL,
            "source_updated_at": official.get("updatedAt") or official.get("publishedAt", ""),
            "source_checked_at": checked_at, "package_names": "\n".join(packages),
            "transports": " ".join(sorted(transports)),
        })


def download_registry(destination: Path) -> Path:
    rows, seen, cursor = [], set(), ""
    checked_at = datetime.now(timezone.utc).isoformat()
    for _ in range(1_000):
        page = registry_page(cursor)
        rows.extend(registry_rows(page, checked_at))
        if len(rows) > MAX_CATALOG_ROWS:
            raise ValueError("registry exceeds row limit")
        cursor = page.get("metadata", {}).get("nextCursor")
        if not cursor:
            break
        if not isinstance(cursor, str) or len(cursor) > 8_000 or cursor in seen:
            raise ValueError("invalid or repeated registry cursor")
        seen.add(cursor)
    else:
        raise ValueError("registry exceeds page limit")
    if not rows:
        raise ValueError("registry returned no active servers")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, delete=False, encoding="utf-8") as handle:
            temporary = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        temporary.replace(destination)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return destination


def read_metadata(path: Path, root: Path) -> dict:
    """Read a bounded JSON file only within the selected catalog or project."""
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("metadata path escapes selected folder")
    relative = path.relative_to(root)
    if any((root.joinpath(*relative.parts[:index])).is_symlink() for index in range(1, len(relative.parts) + 1)):
        raise ValueError("metadata symlinks are not supported")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("metadata exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    return value


def marketplace_rows(root: Path):
    """Read a selected Codex/Claude marketplace checkout; listings are not installations."""
    root = root.expanduser().absolute()
    if root == Path(root.anchor) or root.is_symlink() or not root.is_dir():
        raise ValueError("select a non-symlink marketplace directory")
    manifests = [root / ".agents/plugins/marketplace.json", root / ".claude-plugin/marketplace.json"]
    manifest = next((path for path in manifests if path.is_file()), None)
    if manifest is None:
        raise ValueError("no supported marketplace manifest found")
    data = read_metadata(manifest, root)
    entries = data.get("plugins")
    if not isinstance(entries, list) or len(entries) > 1_000:
        raise ValueError("invalid marketplace plugin list")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError("invalid marketplace entry")
        source = entry.get("source")
        relative = source.get("path") if isinstance(source, dict) and source.get("source") == "local" else source
        detail = entry
        if isinstance(relative, str) and relative.startswith("./"):
            plugin_root = root / relative
            for folder in (".codex-plugin", ".claude-plugin"):
                path = plugin_root / folder / "plugin.json"
                if path.is_file():
                    detail = read_metadata(path, root)
                    break
        keywords = detail.get("keywords", [])
        yield normalize({
            "id": f"plugin:{data.get('name', 'marketplace')}:{entry['name']}",
            "name": entry["name"], "kind": "plugin",
            "plugin_key": f"{entry['name']}@{data.get('name', 'marketplace')}",
            "description": detail.get("description", ""),
            "task_text": " ".join(item for item in keywords if isinstance(item, str)) if isinstance(keywords, list) else "",
            "github_url": detail.get("repository", "") if isinstance(detail.get("repository", ""), str) else "",
            "source_name": "Selected plugin marketplace",
            "source_url": detail.get("homepage", ""),
            "source_checked_at": datetime.now(timezone.utc).isoformat(),
            "requirements": "Verify plugin runtime, client support, and any required credentials.",
        })


def builtin_rows():
    yield from read_catalog(Path(__file__).with_name("capabilities.jsonl"))


def cache_path(source: str) -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "toolfit" / f"{source}.jsonl"
