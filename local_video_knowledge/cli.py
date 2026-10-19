"""Small machine-readable CLI; diagnostics and progress stay on stderr."""

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

from . import __version__, config


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="lvk", description="Transcribe local recordings for your Obsidian vault.")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--json", action="store_true", help="Print one JSON result")
    commands = root.add_subparsers(dest="command", required=True)
    start = commands.add_parser("transcribe", help="Start or resume transcription of a file or folder")
    start.add_argument("path", type=Path)
    start.add_argument("--workdir", type=Path, help="Exact directory, named lvk_<id>")
    start.add_argument("--foreground", action="store_true", help="Transcribe in this process instead of a background worker")
    state = commands.add_parser("status", help="Report progress; optionally wait for completion")
    state.add_argument("workdir", type=Path)
    state.add_argument("--wait", type=float, default=0, help="Seconds to wait for completion (at most 540)")
    halt = commands.add_parser("stop", help="Stop a running transcription; finished files are kept")
    halt.add_argument("workdir", type=Path)
    check = commands.add_parser("check", help="Validate notes and links")
    check.add_argument("notes", type=Path, nargs="+")
    check.add_argument("--vault", required=True, type=Path)
    clean = commands.add_parser("clean", help="Release a lease; remove the workdir after its last lease")
    clean.add_argument("workdir", help="Exact absolute workdir returned by transcribe")
    clean.add_argument("--lease", required=True, help="Lease token returned by that transcribe")
    commands.add_parser("doctor", help="Check installed dependencies, model, vault and skill")
    settings = commands.add_parser("config", help="Read or write user configuration")
    settings.add_argument("action", choices=("get", "set"), nargs="?", default="get")
    settings.add_argument("key", nargs="?", choices=tuple(config.DEFAULTS))
    settings.add_argument("value", nargs="?")
    for command in commands.choices.values():
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    return root


def execute(args) -> dict:
    if args.command == "config":
        if args.action == "set":
            if args.key is None or args.value is None:
                raise ValueError("Usage: lvk config set <key> <value>")
            return config.set_value(args.key, args.value)
        if args.value is not None:
            raise ValueError("config get does not accept a value")
        return {args.key: config.get(args.key)} if args.key else config.load()
    if args.command == "transcribe":
        from .job import start
        return start(args.path, args.workdir, args.foreground)
    if args.command == "status":
        from .job import status
        return status(args.workdir, args.wait)
    if args.command == "stop":
        from .job import stop
        return stop(args.workdir)
    if args.command == "check":
        from .check import validate_notes
        return validate_notes(args.notes, args.vault, config.get("no_dashes"))
    if args.command == "clean":
        from .job import clean
        return clean(args.workdir, args.lease)
    if args.command == "doctor":
        from .doctor import diagnose
        return diagnose()
    raise ValueError("Unknown command")


def minutes(seconds) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60} min {seconds % 60:02} s"


def display(result: dict, command: str):
    if command == "doctor":
        color = sys.stdout.isatty()
        for check in result["checks"]:
            label = "OK" if check["ok"] else "FAIL"
            if color:
                label = f"\033[{32 if check['ok'] else 31}m{label}\033[0m"
            print(f"{label} {check['name']}: {check['detail']}")
    elif command == "check":
        for item in result["files"]:
            print(f"{'OK' if item['ok'] else 'FAIL'} {item['path']}: {item['lines']} non-blank lines")
            for error in item["errors"]:
                print(f"  {error}")
    elif command in {"transcribe", "status"}:
        print(f"{result['state']}: {result['finished']} of {result['files']} files, "
              f"{minutes(result['total_duration'])} of audio")
        if result.get("current"):
            print(f"now: {result['current']}" + (f", about {minutes(result['eta_seconds'])} left" if result.get("eta_seconds") else ""))
        print(f"workdir: {result['workdir']}")
        if result.get("lease"):
            print(f"lease: {result['lease']}")
        if result.get("all_transcripts"):
            print(f"transcripts: {result['all_transcripts']}")
        for error in result.get("errors", []):
            print(f"Warning: {error['file']}: {error['error']}", file=sys.stderr)
        if result.get("error"):
            print(f"Note: {result['error']}", file=sys.stderr)
    elif command == "clean":
        print(f"{'Removed' if result['removed'] else 'Lease released; workdir retained'}: {result['workdir']}")
    else:
        for key, value in result.items():
            print(f"{key}: {str(value).lower() if isinstance(value, bool) else value}")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        with redirect_stdout(sys.stderr):
            result = execute(args)
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) or "Interrupted. Finished files are kept for retry."
        if args.json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=True))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        display(result, args.command)
    failed = result.get("state") in {"failed", "stopped"} and args.command in {"transcribe", "status"}
    return 1 if failed or not result.get("ok", True) else 0


if __name__ == "__main__":
    raise SystemExit(main())
