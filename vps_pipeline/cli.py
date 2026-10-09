"""Explicit, finite local operations; network collection requires an opt-in."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def _read_json(path: str) -> dict:
    source = Path(path)
    with source.open("rb") as stream:
        payload = stream.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("JSON file exceeds the 4 MiB limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Non-finite JSON number")
    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite JSON number")
        return result
    try:
        value = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=floating)
    except RecursionError:
        raise ValueError("JSON nesting exceeds the supported limit") from None
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local VPS review evidence pipeline")
    parser.add_argument("--data", default="./var", help="private data directory (default: ./var)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="initialize the private data directory")
    add = commands.add_parser("add", help="enqueue a public NodeSeek first-post URL")
    add.add_argument("url")
    commands.add_parser("list", help="list jobs and their current state")
    show = commands.add_parser("show", help="inspect one job")
    show.add_argument("id")
    legacy = commands.add_parser("import-legacy", help="privately import a verified historical archive without new AI review")
    legacy.add_argument("manifest", help="directory-based assets/<post_id>/manifest.json; ZIP input is not supported")
    legacy.add_argument("--analysis", help="historical analysis JSON; defaults to sibling analysis.json")
    commands.add_parser("list-legacy", help="list read-only historical imports separately from accepted jobs")
    legacy_show = commands.add_parser("show-legacy", help="read one immutable historical import")
    legacy_show.add_argument("id")
    ingest = commands.add_parser("ingest", help="import a saved first-post HTML page")
    ingest.add_argument("id")
    ingest.add_argument("html", help="local HTML file")
    ingest.add_argument("--resources", metavar="JSON_FILE", help="JSON object mapping source URLs to local files")
    archive_ingest = commands.add_parser("ingest-archive", help="copy an existing verified archive offline for fresh review")
    archive_ingest.add_argument("id")
    archive_ingest.add_argument("manifest", help="assets/<post_id>/manifest.json; preserves original bytes, no ZIP input")
    task = commands.add_parser("task", help="export a ZIP for real assistant evidence review")
    task.add_argument("id")
    task.add_argument("output", help="output ZIP path")
    submit = commands.add_parser("submit", help="validate and import an analysis envelope")
    submit.add_argument("id")
    submit.add_argument("file", help="analysis envelope JSON file")
    for name in ("retry", "cancel"):
        sub = commands.add_parser(name, help=f"{name} one job")
        sub.add_argument("id")
    commands.add_parser("recover", help="recover jobs interrupted by a stopped process")
    collect = commands.add_parser("collect", help="collect a finite number of queued jobs")
    collect.add_argument("--limit", type=int, default=1, help="maximum jobs in this run (1-100)")
    collect.add_argument("--allow-network", action="store_true", help="explicitly authorize this finite network run")
    export = commands.add_parser("export-public", help="export the facts-only filter website safely (alias of export-v5); never publish")
    export.add_argument("output")
    evidence = commands.add_parser("export-evidence", help="PRIVATE local evidence dump, including original source files; do not publish")
    evidence.add_argument("output")
    catalog = commands.add_parser("export-v5", help="export the integrated facts-only filter website to a separate directory; never publish")
    catalog.add_argument("output")
    serve = commands.add_parser("serve", help="run the private loopback management interface")
    serve.add_argument("--host", choices=("127.0.0.1", "::1"), default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        if not args.allow_network:
            parser.error("collect requires --allow-network; no network request was made")
        if not 1 <= args.limit <= 100:
            parser.error("collect --limit must be between 1 and 100")
    if args.command == "serve" and not 0 <= args.port <= 65535:
        parser.error("serve --port must be between 0 and 65535")
    try:
        from .store import Store

        # Store must inspect the original path before any symlink is resolved.
        data_root = Path(args.data).expanduser().absolute()
        store = Store(data_root)
        command = args.command
        if command == "init":
            result = {"status": "ready", "data_root": str(data_root)}
        elif command == "add":
            result = store.enqueue(args.url)
        elif command == "list":
            result = store.list_jobs()
        elif command == "show":
            result = store.get_job(args.id)
        elif command == "import-legacy":
            result = store.import_legacy(args.manifest, args.analysis)
        elif command == "list-legacy":
            result = store.list_legacy()
        elif command == "show-legacy":
            result = store.get_legacy(args.id)
        elif command == "ingest":
            resources = _read_json(args.resources) if args.resources else None
            if resources is not None and not all(isinstance(k, str) and isinstance(v, str) for k, v in resources.items()):
                raise ValueError("resources must map URL strings to local path strings")
            result = store.import_html(args.id, Path(args.html), resources=resources)
        elif command == "ingest-archive":
            result = store.import_archive(args.id, Path(args.manifest))
        elif command == "task":
            result = store.export_task(args.id, Path(args.output))
        elif command == "submit":
            result = store.submit(args.id, _read_json(args.file))
        elif command == "retry":
            result = store.retry(args.id)
        elif command == "cancel":
            result = store.cancel(args.id)
        elif command == "recover":
            result = store.recover()
        elif command == "collect":
            result = store.collect(limit=args.limit)
        elif command == "export-evidence":
            result = store.export_public(Path(args.output))
        elif command in {"export-public", "export-v5"}:
            from .catalog import export_catalog
            result = export_catalog(store,Path(args.output))
        elif command == "serve":
            from .server import serve

            serve(store, data_root, host=args.host, port=args.port)
            return 0
        else:
            parser.error("unknown command")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
