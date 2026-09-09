"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import (
    collect_context,
    default_cache_path,
    download_catalog,
    enrich_candidates,
    rank_candidates,
    render_report,
    render_review_config,
)

from .catalogs import builtin_rows, cache_path, download_registry, marketplace_rows, read_catalog


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="toolfit",
        description="Find tools and agent capabilities that fit your work.",
    )
    result.add_argument("paths", nargs="+", type=Path, help="Project folders to scan")
    result.add_argument("--catalog", type=Path, action="append", default=[], help="Add a local ToolFit or ATE JSONL catalog; repeatable")
    result.add_argument("--source", choices=["ate", "registry", "builtin"], action="append", help="Catalog source; repeat to combine (default: all, or local catalogs only when supplied)")
    result.add_argument("--marketplace", type=Path, action="append", default=[], help="Add a local Codex or Claude plugin marketplace checkout; repeatable")
    result.add_argument("--task", default="", help="Work you want to accomplish; matched locally and included in the report")
    result.add_argument("--refresh-catalog", action="store_true", help="Refresh selected remote catalog caches")
    result.add_argument("--top", type=int, default=10, help="Candidates per project (default: 10)")
    result.add_argument("--max-files", type=int, default=1_000, help="Maximum filenames per project")
    result.add_argument(
        "--include-agent-configs",
        action="store_true",
        help="Read recognized home agent folders, MCP server names, enabled plugin keys, and skill metadata",
    )
    result.add_argument("--offline", action="store_true", help="Use built-in, local, and cached catalogs without network requests")
    result.add_argument("--output", type=Path, help="Write Markdown to this file")
    result.add_argument(
        "--review-config",
        type=Path,
        help="Write an inert, read-only-first MCP configuration review bundle",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    arguments = argument_parser.parse_args(argv)
    if arguments.top < 1 or arguments.top > 100:
        argument_parser.error("[ATE100] --top must be between 1 and 100. Choose a whole number in that range")
    if arguments.output and arguments.review_config:
        if arguments.output.expanduser().resolve() == arguments.review_config.expanduser().resolve():
            argument_parser.error("[ATE100] --output and --review-config must use different files")
    if len(arguments.task) > 4_000:
        argument_parser.error("[ATE100] --task must contain at most 4000 characters")
    if arguments.offline and arguments.refresh_catalog:
        argument_parser.error("[ATE100] --offline and --refresh-catalog cannot be combined")
    rows, source_status = [], []
    for catalog in arguments.catalog:
        if not catalog.is_file() and arguments.offline:
            argument_parser.error(
                f"[ATE101] The offline catalog was not found at {catalog}. "
                "Run without --offline to download remote sources, or pass --catalog with an existing file"
            )
        try:
            loaded = list(read_catalog(catalog))
        except (OSError, ValueError, TypeError) as error:
            argument_parser.error(
                f"[ATE104] Catalog could not be read: {type(error).__name__}. "
                "Pass --catalog with a valid ATE JSONL or ToolFit JSONL file"
            )
        rows.extend(loaded)
        source_status.append(f"Local catalog: {len(loaded)} records; publisher dates are unverified")
    for marketplace in arguments.marketplace:
        try:
            loaded = list(marketplace_rows(marketplace))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            argument_parser.error(f"[ATE104] Marketplace could not be read: {type(error).__name__}. Select a valid local marketplace checkout")
        rows.extend(loaded)
        source_status.append(f"Selected plugin marketplace: {len(loaded)} records; listings do not establish installation")
    sources = list(dict.fromkeys(arguments.source or ([] if arguments.catalog or arguments.marketplace else ["builtin", "ate", "registry"])))
    for source in sources:
        if source == "builtin":
            loaded = list(builtin_rows())
            rows.extend(loaded)
            source_status.append(f"ToolFit maintained catalog: {len(loaded)} records; review dates are attached to candidates")
            continue
        path = default_cache_path() if source == "ate" else cache_path("registry")
        try:
            if not arguments.offline and (arguments.refresh_catalog or not path.is_file()):
                print(f"Preparing {source} catalog...", file=sys.stderr)
                if source == "ate":
                    download_catalog(path, refresh=arguments.refresh_catalog)
                else:
                    download_registry(path)
            loaded = list(read_catalog(path))
            checked = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            for row in loaded:
                row.setdefault("source_checked_at", checked)
            rows.extend(loaded)
            source_status.append(f"{source}: {len(loaded)} cached records; cache written {checked}")
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as error:
            message = f"{source}: unavailable ({type(error).__name__}); recommendations omit this source"
            source_status.append(message)
            print(f"[ATE102] {message}. Retry online or supply a local catalog.", file=sys.stderr)

    reports: list[str] = []
    review_bundles: list[str] = []
    repository_cache: dict = {}
    for supplied in arguments.paths:
        try:
            context = collect_context(
                supplied,
                max_files=max(1, arguments.max_files),
                include_agent_configs=arguments.include_agent_configs,
                task=arguments.task,
            )
        except ValueError as error:
            print(
                f"[ATE103] Skipped {supplied}: {error}. Choose an existing project directory.",
                file=sys.stderr,
            )
            continue
        context.source_status = source_status
        candidates = rank_candidates(context, [*rows, *context.available_rows], limit=arguments.top)
        enrich_candidates(
            candidates,
            offline=arguments.offline,
            repository_cache=repository_cache,
        )
        reports.append(render_report(context, candidates))
        review_bundles.append(render_review_config(context, candidates))
    if not reports:
        print(
            "[ATE105] No project was scanned. Correct the listed project paths and run the command again.",
            file=sys.stderr,
        )
        return 2
    rendered = "\n\n---\n\n".join(reports)
    if arguments.output:
        try:
            arguments.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError as error:
            print(
                f"[ATE106] The report could not be written to {arguments.output}: "
                f"{type(error).__name__}. The output may be incomplete. Choose a new writable output path and run the command again.",
                file=sys.stderr,
            )
            return 2
        print(f"Wrote {arguments.output}", file=sys.stderr)
    else:
        print(rendered)
    if arguments.review_config:
        try:
            arguments.review_config.write_text(
                "\n\n---\n\n".join(review_bundles) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            print(
                f"[ATE107] The configuration review bundle could not be written to {arguments.review_config}: "
                f"{type(error).__name__}. No client configuration was changed. Choose a new writable path and run the command again.",
                file=sys.stderr,
            )
            return 2
        print(f"Wrote inert configuration review bundle to {arguments.review_config}", file=sys.stderr)
    return 0
