"""Evidence of declared packages, local skills, and project-native features."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from .core import MAX_FILE_BYTES


def package_names(path: Path) -> set[str]:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            return set()
        raw = path.read_text(encoding="utf-8")
        if path.name == "package.json":
            value = json.loads(raw)
            return {
                name.lower() for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
                for name in (value.get(key, {}) if isinstance(value.get(key), dict) else {})
            }
        if path.name == "pyproject.toml":
            value = tomllib.loads(raw)
            project = value.get("project", {})
            groups = project.get("optional-dependencies", {})
            dependencies = list(project.get("dependencies", []))
            for entries in groups.values() if isinstance(groups, dict) else ():
                if isinstance(entries, list):
                    dependencies.extend(entries)
            for entries in value.get("dependency-groups", {}).values():
                if isinstance(entries, list):
                    dependencies.extend(entries)
            return {match[0].lower() for item in dependencies if isinstance(item, str)
                    if (match := re.match(r"[A-Za-z0-9][A-Za-z0-9_.-]*", item))}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return set()


def skill_rows(root: Path, limit: int = 1_000):
    """Read names and descriptions from direct SKILL.md children; never read skill bodies."""
    if root.is_symlink() or not root.is_dir() or root.parent.is_symlink():
        return
    for directory in sorted(root.iterdir())[:limit]:
        path = directory / "SKILL.md"
        if directory.is_symlink() or not directory.is_dir() or path.is_symlink():
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            # Only the short frontmatter prefix is needed. No YAML execution or external parser.
            with path.open(encoding="utf-8") as handle:
                prefix = handle.read(8_192)
            if not prefix.startswith("---\n") or "\n---" not in prefix[4:]:
                continue
            frontmatter = prefix[4:].split("\n---", 1)[0]
            metadata = {}
            for key in ("name", "description"):
                match = re.search(rf"^{key}:\s*([^\n]+)", frontmatter, re.MULTILINE)
                if match:
                    value = match[1].strip().strip('"\'')
                    if value not in {"|", ">", "|-", ">-"}:
                        metadata[key] = value[:2_000]
            if not metadata.get("description"):
                continue
            yield {
                "kind": "skill", "tool_name": metadata.get("name", directory.name),
                "server_name": "Local skill", "tool_description": metadata["description"],
                "capability_id": "skill:" + metadata.get("name", directory.name),
                "source_name": "Local skill metadata", "availability": "present",
                "availability_evidence": "SKILL.md found in a selected skill directory; client loading not tested",
                "requirements": "Check the skill instructions, required tools, and client loading.",
            }
        except (OSError, UnicodeError):
            continue


def availability(context, row: dict) -> tuple[str, str]:
    if row.get("availability") == "present":
        return "present", row["availability_evidence"]
    kind = row.get("kind", "mcp")
    name = str(row.get("server_name", "")).lower()
    aliases = set(str(row.get("package_names", "")).lower().splitlines()) - {""}
    if kind == "plugin" and row.get("plugin_key", "").lower() in context.enabled_plugins:
        return "configured", "Exact plugin key is enabled in a recognized configuration; runtime not tested"
    if kind == "mcp" and name in context.installed_servers:
        return "configured", "Exact MCP server name is configured; enabled state and operation not tested"
    if aliases.intersection(context.declared_packages):
        return "declared", "Exact package name appears in a dependency manifest; installation and operation not tested"
    if kind == "native":
        requirement = row.get("capability_id")
        if requirement == "native:github-actions" and "Continuous integration" in context.workflows:
            return "present", "GitHub Actions workflow directory exists; workflow behavior not tested"
        if requirement == "native:unittest" and "python" in context.terms:
            return "built in", "Python source detected; unittest is included with Python"
    return "new", "No exact availability evidence found in the scanned scope"


def configured_plugins(path: Path) -> set[str]:
    """Read explicitly enabled plugin names; ignore commands, hooks and all other values."""
    try:
        if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            return set()
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw) if path.suffix == ".json" else tomllib.loads(raw)
        plugins = value.get("enabledPlugins", {}) if path.suffix == ".json" else value.get("plugins", {})
        if not isinstance(plugins, dict):
            return set()
        return {name.lower() for name, config in plugins.items()
                if config is True or isinstance(config, dict) and config.get("enabled") is True}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()
