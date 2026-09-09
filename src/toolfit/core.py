"""Local metadata collection, ranking, and candidate screening."""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping


DATASET = "CohereLabs/ATE"
DATASET_API = "https://datasets-server.huggingface.co"
USER_AGENT = "toolfit/0.2.0 (+https://github.com/admin-raintree/toolfit)"
MAX_FILE_BYTES = 256_000
MAX_FILES = 1_000
MAX_CATALOG_ROWS = 100_000
TOKEN_RE = re.compile(r"[a-z][a-z0-9+#.-]{2,}")
URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")

IGNORED_PARTS = {
    ".git", ".github", ".hg", ".svn", ".next", ".venv", "venv", "__pycache__",
    "build", "dist", "node_modules", "target", "vendor", ".cache",
}
SENSITIVE_NAMES = {
    ".env", ".env.local", ".npmrc", ".pypirc", "credentials.json", "secrets.json",
    "id_rsa", "id_ed25519", "known_hosts", "authorized_keys",
}
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "cargo.toml", "go.mod",
    "gemfile", "composer.json", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "mcp.json", ".mcp.json", ".claude.json", "config.toml", "agents.md", "claude.md", "cursor.md", ".cursorrules",
    "readme.md", "readme.txt",
}
STOP_WORDS = {
    "about", "after", "again", "against", "all", "also", "and", "any", "are", "because",
    "before", "being", "both", "build", "can", "could", "does", "each", "final", "first",
    "for", "from", "have", "how", "into", "its", "may", "more", "most", "must", "new",
    "next", "not", "only", "other", "our", "over", "project", "required", "should", "some",
    "than", "that", "the", "their", "then", "there", "these", "they", "this", "through",
    "tool", "tools", "under", "use", "using", "was", "were", "when", "where", "which",
    "will", "with", "would", "you", "your",
}
CAPABILITY_EXPANSIONS = {
    "react": {"frontend", "browser", "typescript", "accessibility"},
    "nextjs": {"frontend", "browser", "typescript", "deployment"},
    "typescript": {"javascript", "frontend", "node"},
    "postgres": {"database", "sql", "query"},
    "mysql": {"database", "sql", "query"},
    "sqlite": {"database", "sql", "query"},
    "pytest": {"testing", "python", "quality"},
    "playwright": {"browser", "testing", "accessibility"},
    "github": {"repository", "issues", "pull", "deployment"},
    "docker": {"container", "deployment", "infrastructure"},
    "terraform": {"infrastructure", "cloud", "deployment"},
    "pdf": {"document", "extract", "convert"},
    "spreadsheet": {"excel", "data", "table"},
    "analytics": {"data", "chart", "visualization"},
}
FILE_CAPABILITIES = {
    ".py": {"python", "testing", "code"},
    ".js": {"javascript", "node", "code"},
    ".jsx": {"javascript", "react", "frontend"},
    ".ts": {"typescript", "node", "code"},
    ".tsx": {"typescript", "react", "frontend"},
    ".swift": {"swift", "apple", "ios"},
    ".go": {"golang", "backend", "code"},
    ".rs": {"rust", "backend", "code"},
    ".md": {"markdown", "documentation"},
    ".pdf": {"pdf", "document"},
    ".sql": {"sql", "database"},
}
OPPORTUNITY_PROFILES = {
    "Web quality": (
        {"react", "nextjs", "frontend", "typescript", "javascript", "website", "html", "css"},
        {"accessibility", "browser", "playwright", "screenshot", "visual", "testing", "performance", "lighthouse"},
    ),
    "Documentation and knowledge": (
        {"documentation", "markdown", "docs", "knowledge", "standards", "readme"},
        {"documentation", "markdown", "search", "index", "links", "convert", "summarize", "knowledge"},
    ),
    "Database operations": (
        {"database", "sql", "postgres", "mysql", "sqlite", "prisma", "schema"},
        {"database", "query", "schema", "migration", "postgres", "sql", "backup", "performance"},
    ),
    "Security review": (
        {"security", "scanner", "authentication", "authorization", "vulnerability", "audit"},
        {"security", "vulnerability", "audit", "scan", "dependency", "permissions", "secrets"},
    ),
    "Media processing": (
        {"music", "audio", "video", "image", "media", "podcast"},
        {"audio", "transcribe", "metadata", "video", "image", "convert", "caption"},
    ),
    "Financial analysis": (
        {"finance", "financial", "portfolio", "trading", "market", "accounting"},
        {"finance", "market", "price", "portfolio", "chart", "analysis", "transaction"},
    ),
    "Agent engineering": (
        {"agent", "agents", "mcp", "codex", "claude", "cursor", "prompt"},
        {"agent", "mcp", "evaluation", "trace", "prompt", "memory", "observability", "testing"},
    ),
    "Code maintenance": (
        {"python", "javascript", "typescript", "golang", "rust", "swift", "code", "backend"},
        {"testing", "review", "debug", "refactor", "coverage", "dependency", "analysis", "quality"},
    ),
}
WORKFLOW_PROFILES = {
    "Test and quality checks": {"test", "tests", "pytest", "playwright", "jest", "lint", "ruff", "coverage"},
    "Build and package": {"build", "package", "compile", "bundle", "setuptools", "docker"},
    "Continuous integration": {"workflow", "workflows", "actions", "ci", "github"},
    "Documentation maintenance": {"docs", "documentation", "readme", "markdown", "mkdocs"},
    "Database changes": {"migration", "migrations", "alembic", "schema", "database", "sql"},
    "Deployment and operations": {"deploy", "deployment", "release", "terraform", "docker", "cloud"},
}
CLIENT_TRANSPORTS = {
    "Codex": {"stdio", "http"},
    "Claude Code": {"stdio", "http", "sse", "websocket"},
    "Cursor": {"stdio", "http", "sse"},
    "Grok Build": {"stdio", "http"},
}
TRANSPORT_PATTERNS = {
    "stdio": re.compile(
        r"\bstdio\b|StdioServerTransport|--transport[ =]+stdio|"
        r"(?:claude|codex|grok)\s+mcp\s+add\s+[^\r\n]*\s--\s|"
        r'''["']mcpServers["']\s*:\s*\{[\s\S]{0,2000}["']command["']\s*:''',
        re.IGNORECASE,
    ),
    "http": re.compile(r"streamable[ -]?http|StreamableHTTPServerTransport|--transport[ =]+http", re.IGNORECASE),
    "sse": re.compile(r"server[- ]sent events|SSEServerTransport|--transport[ =]+sse", re.IGNORECASE),
    "websocket": re.compile(r"\bwebsocket\b|\bweb socket\b|--transport[ =]+websocket", re.IGNORECASE),
}
PERMISSION_SIGNALS = {
    "credentials": {"credential", "credentials", "secret", "token", "oauth", "authentication"},
    "filesystem": {"file", "files", "filesystem", "directory", "folder"},
    "code execution": {"execute", "execution", "shell", "terminal", "command", "script", "sudo"},
    "network": {"network", "http", "browser", "download", "upload", "api"},
    "database": {"database", "query", "schema", "migration", "postgres", "mysql", "sqlite"},
    "communications": {"email", "message", "send", "publish", "post"},
    "payments or trading": {"payment", "purchase", "refund", "trade", "transaction"},
    "deployment": {"deploy", "deployment", "infrastructure", "cloud"},
}
AGGREGATOR_MARKERS = {"awesome", "skillranking", "ecosystem", "collection", "directory"}
HIGH_RISK_TERMS = {
    "delete", "irreversible", "payment", "purchase", "refund", "shell", "terminal",
    "credential", "secret", "private-key", "sudo", "deploy", "execute", "execution", "trade",
}
MEDIUM_RISK_TERMS = {
    "create", "edit", "update", "write", "send", "upload", "download", "browser",
    "network", "email", "message", "database", "filesystem",
}
SAFE_REPORT_SIGNALS = (
    set(CAPABILITY_EXPANSIONS)
    | set().union(*CAPABILITY_EXPANSIONS.values())
    | set().union(*(triggers | goals for triggers, goals in OPPORTUNITY_PROFILES.values()))
    | set().union(*FILE_CAPABILITIES.values())
)


@dataclass
class ProjectContext:
    root: Path
    terms: Counter[str] = field(default_factory=Counter)
    metadata_files: list[str] = field(default_factory=list)
    detected_agents: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    workflows: dict[str, list[str]] = field(default_factory=dict)
    installed_servers: set[str] = field(default_factory=set)
    agent_configs_checked: bool = False
    task: str = ""
    task_terms: Counter[str] = field(default_factory=Counter)
    enabled_plugins: set[str] = field(default_factory=set)
    declared_packages: set[str] = field(default_factory=set)
    available_rows: list[dict[str, str]] = field(default_factory=list)
    source_status: list[str] = field(default_factory=list)
    files_seen: int = 0
    files_skipped: int = 0


@dataclass
class Candidate:
    score: float
    row: dict[str, str]
    signals: list[str]
    risk_level: str
    risk_signals: list[str]
    repository: dict[str, object] | None = None
    workflow_fit: list[str] = field(default_factory=list)
    compatibility: dict[str, str] = field(default_factory=dict)
    transport_evidence: dict[str, list[str]] = field(default_factory=dict)
    repository_transport_checked: bool = False
    maintenance: str = "unknown"
    permission_signals: list[str] = field(default_factory=list)
    security_review: str = "required"
    availability: str = "new"
    availability_evidence: str = "No availability evidence"
    task_fit: list[str] = field(default_factory=list)
    provenance: list[dict[str, str]] = field(default_factory=list)


def tokenize(text: str) -> Counter[str]:
    normalized = text.lower().replace("next.js", "nextjs").replace("model context protocol", "mcp")
    return Counter(
        token for token in TOKEN_RE.findall(normalized)
        if token not in STOP_WORDS and not looks_sensitive(token)
    )


def looks_sensitive(token: str) -> bool:
    if len(token) > 30:
        return True
    digits = sum(character.isdigit() for character in token)
    return digits > max(4, len(token) // 3)


def expand_capabilities(terms: Counter[str]) -> None:
    additions: Counter[str] = Counter()
    for term, count in terms.items():
        for related in CAPABILITY_EXPANSIONS.get(term, set()):
            additions[related] += max(1, count // 2)
    terms.update(additions)


def detect_workflows(root: Path, manifest_sources: Mapping[str, str]) -> dict[str, list[str]]:
    """Identify concrete workflow surfaces without retaining commands or file contents."""
    evidence: dict[str, list[str]] = {}
    sources = dict(manifest_sources)
    if (root / "tests").is_dir() or (root / "test").is_dir():
        sources["tests"] = "test directory"
    if (root / ".github" / "workflows").is_dir():
        sources["workflow"] = "GitHub Actions configuration"
    if any((root / name).exists() for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml")):
        sources["docker"] = "container configuration"
    if any((root / name).is_dir() for name in ("docs", "documentation")):
        sources["docs"] = "documentation directory"
    if any((root / name).is_dir() for name in ("migrations", "alembic")):
        sources["migration"] = "migration directory"

    observed_terms = set(sources)
    for workflow, triggers in WORKFLOW_PROFILES.items():
        hits = sorted(observed_terms.intersection(triggers))
        if hits:
            workflow_sources = sorted({sources.get(hit, "repository metadata") for hit in hits})
            evidence[workflow] = workflow_sources
    return evidence


def _approved_json_metadata(path: Path, value: object) -> list[str]:
    """Return non-secret JSON metadata. MCP and agent configs contribute keys only."""
    strings: list[str] = []
    lower_name = path.name.lower()

    def keys_only(item: object, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                strings.append(str(key))
                keys_only(child, depth + 1)
        elif isinstance(item, list):
            for child in item[:100]:
                if isinstance(child, (dict, list)):
                    keys_only(child, depth + 1)

    if lower_name in {"mcp.json", ".mcp.json"} or any(
        part in {".codex", ".claude", ".cursor", ".grok"} for part in path.parts
    ):
        keys_only(value)
        return strings

    if lower_name == "package.json" and isinstance(value, dict):
        for key in ("name", "description"):
            item = value.get(key)
            if isinstance(item, str) and len(item) <= 500:
                strings.append(item)
        keywords = value.get("keywords", [])
        if isinstance(keywords, list):
            strings.extend(str(item) for item in keywords[:100])
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            item = value.get(key, {})
            if isinstance(item, dict):
                strings.extend(str(name) for name in item)
        scripts = value.get("scripts", {})
        if isinstance(scripts, dict):
            strings.extend(str(name) for name in scripts)
        return strings

    keys_only(value)
    return strings


def metadata_terms(path: Path, workflow_sources: dict[str, str] | None = None) -> Counter[str]:
    try:
        if path.is_symlink() or path.name.lower() in SENSITIVE_NAMES:
            return Counter()
        if path.stat().st_size > MAX_FILE_BYTES:
            return Counter()
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return Counter()

    lower_name = path.name.lower()
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return Counter()
        if lower_name == "package.json" and isinstance(parsed, dict) and workflow_sources is not None:
            scripts = parsed.get("scripts", {})
            if isinstance(scripts, dict):
                for name in scripts:
                    for token in tokenize(str(name)):
                        workflow_sources.setdefault(token, "package.json script name")
        return tokenize(" ".join(_approved_json_metadata(path, parsed)))
    if lower_name in {"agents.md", "claude.md", "cursor.md", ".cursorrules", "readme.md", "readme.txt"}:
        headings = [line.lstrip("# ") for line in raw.splitlines() if line.startswith("#")]
        return tokenize(" ".join(headings))
    if lower_name in {"requirements.txt", "go.mod", "gemfile"}:
        safe_lines = [line.split("#", 1)[0] for line in raw.splitlines() if not any(word in line.lower() for word in ("token", "password", "secret"))]
        return tokenize(" ".join(safe_lines))
    if lower_name in {"pyproject.toml", "cargo.toml", "config.toml"}:
        try:
            import tomllib
            parsed = tomllib.loads(raw)
        except (ValueError, TypeError):
            return Counter()
        if lower_name == "pyproject.toml" and workflow_sources is not None:
            tools = parsed.get("tool", {}) if isinstance(parsed, dict) else {}
            for name in tools if isinstance(tools, dict) else ():
                workflow_sources.setdefault(str(name).lower(), "pyproject.toml tool configuration")
            project = parsed.get("project", {}) if isinstance(parsed, dict) else {}
            if isinstance(project, dict) and isinstance(project.get("scripts"), dict) and project["scripts"]:
                workflow_sources.setdefault("package", "Python command entry point")
        return tokenize(" ".join(_approved_json_metadata(path, parsed)))
    return tokenize(" ".join(re.findall(r"^[A-Za-z][A-Za-z0-9_.-]*:", raw, re.MULTILINE)))


def detect_agents() -> list[str]:
    home = Path.home()
    candidates = {
        "Codex": home / ".codex",
        "Claude Code": home / ".claude",
        "Cursor": home / ".cursor",
        "Grok-compatible config": home / ".grok",
    }
    return [name for name, path in candidates.items() if path.is_dir()]


def configured_server_names(path: Path) -> set[str]:
    """Read MCP server keys without retaining commands, arguments, URLs, or credentials."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return set()
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() == ".json":
            value = json.loads(raw)
        else:
            import tomllib
            value = tomllib.loads(raw)
    except (OSError, ValueError, TypeError):
        return set()
    if not isinstance(value, dict):
        return set()
    servers = value.get("mcpServers") or value.get("mcp_servers")
    if not isinstance(servers, dict):
        return set()
    return {str(name).lower() for name in servers}


def detected_server_names() -> set[str]:
    home = Path.home()
    paths = [
        home / ".codex" / "config.toml",
        home / ".claude.json",
        home / ".claude" / "settings.json",
        home / ".cursor" / "mcp.json",
        home / ".grok" / "config.toml",
    ]
    result: set[str] = set()
    for path in paths:
        result.update(configured_server_names(path))
    return result


def collect_context(
    root: Path,
    max_files: int = MAX_FILES,
    include_agent_configs: bool = False,
    task: str = "",
) -> ProjectContext:
    from .available import configured_plugins, package_names, skill_rows
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    if root == Path(root.anchor):
        raise ValueError("refusing to scan a filesystem root; select project folders")

    context = ProjectContext(
        root=root,
        detected_agents=detect_agents() if include_agent_configs else [],
        installed_servers=detected_server_names() if include_agent_configs else set(),
        agent_configs_checked=include_agent_configs,
    )
    context.task = task
    context.task_terms = tokenize(task)
    expand_capabilities(context.task_terms)
    workflow_sources: dict[str, str] = {}
    context.terms.update(tokenize(root.name))
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names
            if name not in IGNORED_PARTS and not (Path(current) / name).is_symlink()
        )
        relative_current = Path(current).relative_to(root)
        if relative_current.parts:
            context.terms.update(tokenize(" ".join(relative_current.parts)))
        for filename in sorted(file_names):
            if context.files_seen >= max_files:
                context.files_skipped += 1
                continue
            context.files_seen += 1
            path = Path(current) / filename
            if filename.lower() in SENSITIVE_NAMES or path.is_symlink():
                context.files_skipped += 1
                continue
            context.terms.update(tokenize(filename))
            for capability in FILE_CAPABILITIES.get(path.suffix.lower(), set()):
                context.terms[capability] += 1
            if filename.lower() in MANIFEST_NAMES:
                context.installed_servers.update(configured_server_names(path))
                context.declared_packages.update(package_names(path))
                terms = metadata_terms(path, workflow_sources)
                if terms:
                    context.terms.update(terms)
                    context.metadata_files.append(str(path.relative_to(root)))
    expand_capabilities(context.terms)
    context.opportunities = [
        name for name, (triggers, _) in OPPORTUNITY_PROFILES.items()
        if set(context.terms).intersection(triggers)
    ]
    context.workflows = detect_workflows(root, workflow_sources)
    for base in [root, *([Path.home()] if include_agent_configs else [])]:
        for config in (".codex/config.toml", ".claude/settings.json"):
            config_path = base / config
            if not config_path.parent.is_symlink():
                context.enabled_plugins.update(configured_plugins(config_path))
        for folder in (".agents/skills", ".codex/skills", ".claude/skills"):
            context.available_rows.extend(skill_rows(base / folder))
    return context


def default_cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    current = base / "toolfit" / "ate.jsonl"
    legacy = base / "ate-mcp-opportunity-scanner" / "onet-good.jsonl"
    return legacy if not current.is_file() and legacy.is_file() else current


def _request_json(endpoint: str, parameters: Mapping[str, str | int], retries: int = 7) -> dict:
    url = f"{DATASET_API}/{endpoint}?{urllib.parse.urlencode(parameters)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    delay = 1.0
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read(10_000_001)
                if len(payload) > 10_000_000:
                    raise RuntimeError("dataset response exceeded the size limit")
                result = json.loads(payload)
            if "error" not in result:
                return result
            last_error = RuntimeError(str(result["error"]))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(delay)
        delay = min(delay * 2, 20)
    raise RuntimeError(f"dataset request failed: {last_error}")


def _download_catalog_via_api(destination: Path) -> Path:
    parameters: dict[str, str | int] = {
        "dataset": DATASET,
        "config": "onet_matches",
        "split": "train",
        "where": '"match_quality"=\'good\'',
        "offset": 0,
        "length": 100,
    }
    first = _request_json("filter", parameters)
    total = int(first.get("num_rows_total", len(first.get("rows", []))))
    if total < 1 or total > MAX_CATALOG_ROWS:
        raise RuntimeError(f"refusing unexpected catalog row count: {total}")
    first_rows = first.get("rows", [])
    page_size = int(first.get("num_rows_per_page") or len(first_rows) or 100)
    pages: dict[int, list[dict]] = {0: first_rows}

    def fetch_page(offset: int) -> tuple[int, list[dict]]:
        page_parameters = dict(parameters)
        page_parameters["offset"] = offset
        page = _request_json("filter", page_parameters)
        return offset, page.get("rows", [])

    offsets = list(range(page_size, total, page_size))
    if offsets:
        with ThreadPoolExecutor(max_workers=min(8, len(offsets))) as executor:
            futures = [executor.submit(fetch_page, offset) for offset in offsets]
            for future in as_completed(futures):
                offset, rows = future.result()
                pages[offset] = rows

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    written = 0
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for offset in sorted(pages):
                rows = pages[offset]
                written += len(rows)
                for wrapped in rows:
                    row = wrapped.get("row", wrapped)
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if written != total:
            raise RuntimeError(f"catalog download returned {written} rows; expected {total}")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def download_catalog(destination: Path, refresh: bool = False) -> Path:
    if destination.is_file() and not refresh:
        return destination
    return _download_catalog_via_api(destination)


def iter_catalog(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def classify_risk(text: str) -> tuple[str, list[str]]:
    terms = set(tokenize(text))
    high = sorted(terms.intersection(HIGH_RISK_TERMS))
    medium = sorted(terms.intersection(MEDIUM_RISK_TERMS))
    if high:
        return "high", high
    if medium:
        return "medium", medium
    return "low", []


def rank_candidates(context: ProjectContext, rows: Iterable[dict[str, str]], limit: int = 20) -> list[Candidate]:
    from .available import availability

    prepared: list[tuple[dict[str, str], Counter[str]]] = []
    document_frequency: Counter[str] = Counter()
    for row in rows:
        required_signals = set(tokenize(row.get("project_signals", "")))
        if required_signals and not required_signals.intersection(set(context.terms) | set(context.task_terms)):
            continue
        description = str(row.get("tool_description") or "").strip()
        server_name = str(row.get("server_name") or "").lower()
        if len(description) < 20 or any(marker in server_name for marker in AGGREGATOR_MARKERS):
            continue
        candidate_terms = tokenize(" ".join(str(row.get(key, "")) for key in (
            "tool_name", "server_name", "tool_description", "task_text", "occupation_title", "requirements"
        )))
        expand_capabilities(candidate_terms)
        prepared.append((row, candidate_terms))
        document_frequency.update(candidate_terms.keys())

    document_count = max(len(prepared), 1)
    ranked: list[Candidate] = []
    context_terms = set(context.terms)
    for row, candidate_terms in prepared:
        opportunity_hits: dict[str, set[str]] = {}
        for name in context.opportunities:
            goals = OPPORTUNITY_PROFILES[name][1]
            hits = set(candidate_terms).intersection(goals)
            if hits:
                opportunity_hits[name] = hits
        weighted: dict[str, float] = {}
        for term in context_terms.intersection(candidate_terms):
            frequency = document_frequency[term]
            if document_count >= 20 and frequency / document_count >= 0.15:
                continue
            inverse_frequency = math.log((document_count + 1) / (frequency + 1)) + 1
            weighted[term] = inverse_frequency * (1 + math.log1p(context.terms[term]))
        task_hits = sorted(set(context.task_terms).intersection(candidate_terms))
        # ponytail: lexical task matching; add semantic ranking only after held-out relevance evaluation.
        if context.task_terms and not task_hits:
            continue
        profile_term_count = len(set().union(*opportunity_hits.values())) if opportunity_hits else 0
        if len(weighted) < 2 and profile_term_count < 2 and not task_hits:
            continue
        numerator = sum(
            weight
            * (math.log((document_count + 1) / (document_frequency[term] + 1)) + 1)
            * (1 + math.log1p(candidate_terms[term]))
            for term, weight in weighted.items()
        )
        norm = math.sqrt(sum(
            ((math.log((document_count + 1) / (document_frequency[term] + 1)) + 1) * (1 + math.log1p(count))) ** 2
            for term, count in candidate_terms.items()
        ))
        score = numerator / max(norm, 1.0)
        score += sum(8.0 + 4.0 * len(hits) for hits in opportunity_hits.values())
        stars = row.get("github_stargazers_count")
        try:
            score += min(math.sqrt(max(float(stars), 0.0)), 50.0) / 2.0
        except (TypeError, ValueError):
            pass
        description = f"{row.get('tool_name', '')} {row.get('tool_description', '')} {row.get('access', '')}"
        risk_level, risk_signals = classify_risk(description)
        candidate_term_set = set(candidate_terms)
        workflow_fit = [
            workflow for workflow, triggers in WORKFLOW_PROFILES.items()
            if workflow in context.workflows and candidate_term_set.intersection(triggers)
        ]
        score += 6.0 * len(workflow_fit) + 20.0 * len(task_hits)
        if risk_level == "high":
            score *= 0.75
        elif risk_level == "medium":
            score *= 0.9
        available, available_evidence = availability(context, row)
        ranked.append(Candidate(
            score=score,
            row=row,
            signals=(
                [f"{name}: {', '.join(sorted(hits))}" for name, hits in opportunity_hits.items()]
                + [
                    term for term in sorted(weighted, key=weighted.get, reverse=True)
                    if term in SAFE_REPORT_SIGNALS
                ]
            )[:8],
            risk_level=risk_level,
            risk_signals=risk_signals,
            workflow_fit=workflow_fit,
            availability=available,
            availability_evidence=available_evidence,
            task_fit=task_hits,
            provenance=[{key: row.get(key, "") for key in (
                "source_name", "source_url", "source_updated_at", "source_checked_at"
            )}],
        ))

    ranked.sort(key=lambda candidate: (
        candidate.availability == "new", -candidate.score,
        str(candidate.row.get("tool_name", "")), str(candidate.row.get("source_name", "")),
    ))
    results: list[Candidate] = []
    seen: dict[tuple, Candidate] = {}
    for candidate in ranked:
        row = candidate.row
        # Never collapse unrelated publishers merely because their tool names match.
        publisher = row.get("github_url") or row.get("server_name") or row.get("source_name", "")
        identity = (row.get("kind", "mcp"), publisher.lower().removesuffix(".git").rstrip("/"),
                    str(row.get("tool_name", "")).lower())
        if identity in seen:
            prior = seen[identity]
            for source in candidate.provenance:
                if source not in prior.provenance:
                    prior.provenance.append(source)
            continue
        seen[identity] = candidate
        results.append(candidate)
    return results[:limit]


def detect_transports(candidate: Candidate) -> list[str]:
    """Return explicit catalog transports; absence means compatibility is unknown."""
    text = " ".join(str(candidate.row.get(key, "")) for key in (
        "tool_description", "task_text", "transports"
    )).lower()
    return sorted(name for name, pattern in TRANSPORT_PATTERNS.items() if pattern.search(text))


def assess_candidate(candidate: Candidate) -> None:
    """Attach bounded compatibility, maintenance, permission, and review evidence."""
    metadata_transports = detect_transports(candidate)
    transports = sorted(set(metadata_transports).union(candidate.transport_evidence))
    for client, supported in CLIENT_TRANSPORTS.items():
        matches = sorted(set(transports).intersection(supported))
        if matches:
            evidence = []
            for transport in matches:
                sources = ([candidate.row.get("source_name", "ATE metadata")] if transport in metadata_transports else []) + candidate.transport_evidence.get(transport, [])
                evidence.append(f"{transport} in {', '.join(dict.fromkeys(sources))}")
            candidate.compatibility[client] = (
                f"possible via {'; '.join(evidence)}; configuration and authentication not tested"
            )
        elif transports:
            candidate.compatibility[client] = (
                f"not established; available evidence identifies {', '.join(transports)}"
            )
        else:
            candidate.compatibility[client] = (
                "unknown; no explicit transport found in catalog or attempted repository metadata"
                if candidate.repository_transport_checked
                else "unknown; catalog metadata does not identify a transport"
            )

    if candidate.row.get("kind", "mcp") != "mcp":
        candidate.compatibility = {"Requirements": candidate.row.get("requirements") or
                                   "Verify runtime, platform and client requirements; operation not tested"}

    repository = candidate.repository or {}
    warnings = [str(item) for item in repository.get("warnings", [])]
    pushed = repository.get("pushed_at") or candidate.row.get("github_pushed_at")
    archived = any("archived" in warning.lower() for warning in warnings) or str(
        candidate.row.get("github_archived", "")
    ).lower() == "true"
    if archived:
        candidate.maintenance = "archived"
    elif isinstance(pushed, str) and pushed:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            candidate.maintenance = "stale" if age_days > 730 else "recently updated" if age_days <= 365 else "aging"
        except (ValueError, TypeError):
            candidate.maintenance = "unknown"
    else:
        candidate.maintenance = "unknown"

    text_terms = set(tokenize(" ".join(str(candidate.row.get(key, "")) for key in (
        "tool_name", "server_name", "tool_description", "task_text", "access"
    ))))
    candidate.permission_signals = sorted(
        category for category, terms in PERMISSION_SIGNALS.items() if text_terms.intersection(terms)
    )
    if candidate.risk_level == "high" or candidate.maintenance in {"archived", "stale"}:
        candidate.security_review = "high priority"
    elif candidate.risk_level == "medium" or warnings or candidate.permission_signals:
        candidate.security_review = "required before use"
    else:
        candidate.security_review = "required; no elevated signal detected"


def resolve_server(mcp_id: str) -> dict[str, object] | None:
    if not re.fullmatch(r"[0-9a-f]{16}", mcp_id):
        return None
    result = _request_json("filter", {
        "dataset": DATASET,
        "config": "servers",
        "split": "train",
        "where": f'"mcp_id"=\'{mcp_id}\'',
        "offset": 0,
        "length": 1,
    }, retries=3)
    rows = result.get("rows", [])
    if not rows:
        return None
    return rows[0].get("row", rows[0])


def _read_public_github_file(repository_url: str, branch: str, filename: str) -> str | None:
    match = URL_RE.match(repository_url)
    if not match or not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", branch):
        return None
    owner, repository = match.groups()
    parts = [urllib.parse.quote(value, safe="") for value in (owner, repository, branch, filename)]
    url = f"https://raw.githubusercontent.com/{'/'.join(parts)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if urllib.parse.urlparse(response.geturl()).hostname != "raw.githubusercontent.com":
                return None
            content = response.read(MAX_FILE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError):
        return None
    if len(content) > MAX_FILE_BYTES:
        return None
    return content.decode("utf-8", errors="ignore")


def repository_transport_evidence(repository_url: str, branch: str) -> dict[str, list[str]]:
    """Read bounded public documentation and package metadata without cloning code."""
    evidence: dict[str, list[str]] = {}
    for filename in ("README.md", "package.json", "pyproject.toml", "server.json", ".mcp.json"):
        text = _read_public_github_file(repository_url, branch, filename)
        if not text:
            continue
        for transport, pattern in TRANSPORT_PATTERNS.items():
            if pattern.search(text):
                evidence.setdefault(transport, []).append(filename)
    return evidence


def github_health(repository_url: str) -> dict[str, object]:
    match = URL_RE.match(repository_url)
    if not match:
        return {"status": "unknown", "warning": "Repository URL is not a recognized GitHub URL."}
    owner, repository = match.groups()
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"status": "unknown", "warning": f"GitHub health lookup failed: {type(error).__name__}"}
    warnings: list[str] = []
    if data.get("archived"):
        warnings.append("Repository is archived.")
    if data.get("license") is None:
        warnings.append("No repository license was detected.")
    pushed = data.get("pushed_at")
    if isinstance(pushed, str):
        try:
            pushed_at = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - pushed_at).days > 730:
                warnings.append("Repository has not been updated for more than two years.")
        except ValueError:
            pass
    return {
        "status": "warning" if warnings else "screened",
        "stars": data.get("stargazers_count"),
        "license": (data.get("license") or {}).get("spdx_id") if isinstance(data.get("license"), dict) else None,
        "pushed_at": pushed,
        "default_branch": data.get("default_branch"),
        "warnings": warnings,
    }


def enrich_candidates(
    candidates: list[Candidate],
    offline: bool = False,
    repository_cache: dict[str, tuple[dict[str, object], dict[str, list[str]]]] | None = None,
) -> None:
    repository_cache = repository_cache if repository_cache is not None else {}
    for candidate in candidates:
        repository_url = candidate.row.get("github_url")
        repository_match = URL_RE.match(str(repository_url or ""))
        if repository_match:
            owner, repository_name = repository_match.groups()
            repository_url = f"https://github.com/{owner}/{repository_name}"
            warnings: list[str] = []
            if str(candidate.row.get("github_archived", "")).lower() == "true":
                warnings.append("ATE recorded this repository as archived.")
            candidate.repository = {
                "url": repository_url,
                "status": "catalog metadata only" if offline else "pending live screen",
                "warnings": warnings,
            }
        else:
            repository_url = None
        if offline:
            assess_candidate(candidate)
            continue
        server: dict[str, object] | None = None
        if not repository_url and candidate.row.get("mcp_id"):
            try:
                server = resolve_server(str(candidate.row.get("mcp_id", "")))
            except RuntimeError:
                server = None
            if server:
                repository_url = str(server.get("github_url") or "")
        resolved_match = URL_RE.match(str(repository_url or ""))
        if resolved_match:
            owner, repository_name = resolved_match.groups()
            repository_url = f"https://github.com/{owner}/{repository_name}"
            if repository_url not in repository_cache:
                health = github_health(repository_url)
                branch = str(health.get("default_branch") or "main")
                repository_cache[repository_url] = (
                    health,
                    repository_transport_evidence(repository_url, branch),
                )
            health, transport_evidence = repository_cache[repository_url]
            candidate.repository = {"url": repository_url, **health}
            candidate.transport_evidence = transport_evidence
            candidate.repository_transport_checked = True
        assess_candidate(candidate)


def _markdown_text(value: object, limit: int | None = None) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()
    if limit is not None:
        text = text[:limit]
    text = text.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "<", ">", "|"):
        text = text.replace(character, f"\\{character}")
    return text


def _source_link(label: str, url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            safe = urllib.parse.quote(url, safe="/:?&=%#")
            return f"[{_markdown_text(label)}]({safe})"
    except ValueError:
        pass
    return _markdown_text(label) + " (no verified source URL)"


def render_report(context: ProjectContext, candidates: list[Candidate]) -> str:
    if context.agent_configs_checked:
        agent_status = ", ".join(context.detected_agents) or "no recognized agent folders found"
    else:
        agent_status = "not requested; pass --include-agent-configs to check"
    lines = [
        f"# ToolFit recommendations for {_markdown_text(context.root.name)}", "",
        "Relevant capabilities with local availability evidence appear before new additions.", "",
        f"Task: {_markdown_text(context.task) if context.task else 'repository overview; no task supplied'}", "",
        f"Scanned locally at {datetime.now(timezone.utc).isoformat()}. No project content was uploaded.",
        "The task and report remain in your terminal or selected output until you delete them.", "",
        f"Agent configuration check: {agent_status}", "",
        f"Considered {context.files_seen} filenames and read {len(context.metadata_files)} approved metadata files.",
        f"Found {len(context.declared_packages)} declared packages, {len(context.installed_servers)} configured MCP server names, {len(context.enabled_plugins)} enabled plugin names, and {len(context.available_rows)} local skills.", "",
        "## Source coverage", "",
        *[f"- {_markdown_text(status)}" for status in context.source_status], "",
        "## Observed workflows", "",
        *([f"- {_markdown_text(name)} ({_markdown_text(', '.join(sources))})"
           for name, sources in context.workflows.items()] or ["- No concrete workflow signal detected."]), "",
        "## Recommendations", "",
    ]
    if not candidates:
        lines.extend(["No candidates matched the available metadata. Try a more specific task or add another catalog.", ""])
    for index, candidate in enumerate(candidates, 1):
        row = candidate.row
        description = re.sub(r"\s+", " ", row.get("tool_description") or row.get("task_text") or "No description").strip()
        if len(description) > 500:
            boundary = description.rfind(" ", 0, 499)
            description = description[:boundary if boundary > 0 else 499] + "…"
        lines.extend([
            f"{index}. **{_markdown_text(row.get('tool_name', 'Unnamed capability'))}** ({_markdown_text(row.get('kind', 'mcp'))})", "",
            f"   - Published description: {_markdown_text(description)}",
            f"   - Availability: {_markdown_text(candidate.availability)}. {_markdown_text(candidate.availability_evidence)}.",
            f"   - Task fit: {_markdown_text(', '.join(candidate.task_fit)) if context.task else 'no task supplied'}",
            f"   - Matching signals: {_markdown_text(', '.join(candidate.signals))}",
            f"   - Repository workflow fit: {_markdown_text(', '.join(candidate.workflow_fit) or 'no direct workflow match')}",
            f"   - Access: {_markdown_text(row.get('access') or 'not specified; verify publisher requirements')}",
            f"   - Permission signals: {_markdown_text(', '.join(candidate.permission_signals) or 'none detected in published metadata')}",
            f"   - Action risk: {candidate.risk_level}; security review: {_markdown_text(candidate.security_review)}",
            f"   - Maintenance: {_markdown_text(candidate.maintenance)}",
        ])
        for source in candidate.provenance or [{key: row.get(key, '') for key in ('source_name', 'source_url', 'source_updated_at', 'source_checked_at')}]:
            lines.extend([
                f"   - Source: {_source_link(source.get('source_name') or 'Unspecified catalog', source.get('source_url', ''))}",
                f"   - Source updated: {_markdown_text(source.get('source_updated_at') or 'unknown')}; retrieved or reviewed: {_markdown_text(source.get('source_checked_at') or 'unknown')}.",
            ])
        for client, result in candidate.compatibility.items():
            lines.append(f"   - {_markdown_text(client)}: {_markdown_text(result)}")
        if candidate.repository:
            lines.append(f"   - Repository: {_source_link('Repository source', str(candidate.repository.get('url', '')))}")
            lines.append(f"   - Repository screen: {_markdown_text(candidate.repository.get('status'))}")
            warnings = candidate.repository.get('warnings') or [candidate.repository.get('warning', '')]
            for warning in warnings:
                if warning:
                    lines.append(f"   - Repository warning: {_markdown_text(warning)}")
        lines.extend([
            "   - Still to verify: publisher identity, required access, runtime or client support, and behavior on this project.",
            f"   - Match score: {candidate.score:.1f}", "",
        ])
    lines.extend([
        "## Interpretation", "",
        "An MCP tool is a callable function. An MCP server provides one or more MCP tools.",
        "Plugins, skills, developer tools, and native features have different setup requirements.", "",
        "These recommendations are discovery leads, not compatibility or security approvals.",
        "Dependency declarations and configuration names do not prove that a capability is installed, enabled, or working.",
        "Transport evidence only suggests possible MCP client compatibility. ToolFit did not install, authenticate to, or run a recommended capability.",
        "ATE matches were classified from descriptions, not tool execution. Source dates describe catalog evidence, not tested compatibility or maintenance approval.",
        "Task fit, risk labels, and permission signals use lexical rules. Scores are ranking values, not probabilities; compare them only within this report.", "",
    ])
    return "\n".join(lines)


def _review_label(value: object) -> str:
    return _markdown_text(value, 240)


def render_review_config(context: ProjectContext, candidates: list[Candidate]) -> str:
    """Render inert client templates for human review without installing a server."""
    candidates = [candidate for candidate in candidates if candidate.row.get("kind", "mcp") == "mcp"]
    lines = [
        "# MCP configuration review bundle",
        "",
        f"Project: `{_review_label(context.root.name)}`",
        "",
        "Every suggested filename ends in `.review`, so no supported client loads it as an MCP configuration. The scanner did not install a package, start a server, change a client setting, or write into the scanned project.",
        "",
        "Before activation, verify the publisher's exact command or URL, replace the read-only placeholder with a documented server-side read-only mode, list every exposed tool, and remove every write-capable tool. Client approval prompts do not make an unknown server read-only.",
        "",
        "## Candidates to review",
        "",
    ]
    for index, candidate in enumerate(candidates, 1):
        name = _review_label(candidate.row.get("tool_name") or "Unnamed tool")
        server = _review_label(candidate.row.get("server_name") or "Unknown server")
        lines.extend([
            f"{index}. **{name}** from **{server}** — workflow: "
            f"{_review_label(', '.join(candidate.workflow_fit) if candidate.workflow_fit else 'no direct match')}; "
            f"risk: {_review_label(candidate.risk_level)}; "
            f"permissions: {_review_label(', '.join(candidate.permission_signals) if candidate.permission_signals else 'none detected')}; "
            f"maintenance: {_review_label(candidate.maintenance)}.",
            *[
                f"   - {_review_label(client)}: {_review_label(result)}"
                for client, result in candidate.compatibility.items()
            ],
            "",
        ])
    if not candidates:
        lines.append("No MCP candidates matched. No client configuration templates were generated.")
        return "\n".join(lines)
    lines.extend([
        "## Reusable client templates",
        "",
        "Replace every placeholder only after selecting and reviewing one candidate above.",
        "",
        "### Codex — `.codex/config.toml.review`",
        "",
        "```toml",
        "[mcp_servers.reviewed-candidate]",
        'command = "REPLACE_WITH_VERIFIED_SERVER_COMMAND"',
        'args = ["REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT"]',
        "enabled = false",
        'enabled_tools = ["REPLACE_WITH_VERIFIED_READ_ONLY_TOOL"]',
        'default_tools_approval_mode = "prompt"',
        "```",
        "",
        "### Claude Code — `.mcp.json.review`",
        "",
        "```json",
        json.dumps({
            "mcpServers": {
                "reviewed-candidate": {
                    "command": "REPLACE_WITH_VERIFIED_SERVER_COMMAND",
                    "args": ["REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT"],
                    "env": {},
                }
            }
        }, indent=2),
        "```",
        "",
        "### Cursor — `.cursor/mcp.json.review`",
        "",
        "```json",
        json.dumps({
            "mcpServers": {
                "reviewed-candidate": {
                    "type": "stdio",
                    "command": "REPLACE_WITH_VERIFIED_SERVER_COMMAND",
                    "args": ["REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT"],
                    "env": {},
                }
            }
        }, indent=2),
        "```",
        "",
        "### Grok Build — `.grok/config.toml.review`",
        "",
        "```toml",
        "[mcp_servers.reviewed-candidate]",
        'command = "REPLACE_WITH_VERIFIED_SERVER_COMMAND"',
        'args = ["REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT"]',
        "enabled = false",
        "```",
        "",
        "## Activation gate",
        "",
        "Do not rename or copy a template until all checks pass:",
        "",
        "- The repository and package identity match the publisher's documentation.",
        "- The server is maintained, licensed, and installed with a pinned version.",
        "- The server-side read-only argument is real and tested. Remove the candidate if no read-only mode exists.",
        "- The exposed tool list contains only reviewed read operations.",
        "- Credentials have the minimum scopes and stay outside the configuration file.",
        "- Network destinations and data retention are acceptable.",
        "- The first run occurs in a disposable test project with approval prompts enabled.",
        "",
    ])
    return "\n".join(lines)
