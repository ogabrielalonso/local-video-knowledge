"""Environment checks that never download a model."""

import importlib
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sys

from . import config
from .media import ffmpeg_path


def skill_marker() -> str:
    return f"<!-- local-video-knowledge:managed installation-id:{config.home()} -->"


def model_cached(name: str) -> str:
    """Report whether the configured model is already downloaded, without fetching it."""
    from faster_whisper.utils import download_model

    try:
        path = download_model(name, local_files_only=True)
    except Exception:
        return f"{name} not downloaded yet; the first transcription downloads it (large-v3-turbo is about 1.6 GB)"
    return f"{name} ready at {path}"


def diagnose() -> dict:
    checks = []

    def check(name, function):
        try:
            detail = function()
            checks.append({"name": name, "ok": True, "detail": str(detail)})
        except Exception as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)})

    def python_check():
        if sys.version_info < (3, 12):
            raise ValueError("Python 3.12 or newer required")
        return sys.version.split()[0]

    def ffmpeg_check():
        result = subprocess.run([ffmpeg_path(), "-version"], check=True, capture_output=True, text=True, timeout=20)
        return result.stdout.splitlines()[0]

    def vault_check():
        value = config.get("vault")
        if not value:
            raise ValueError("Unset. Run: lvk config set vault /path/to/vault")
        if not (Path(value) / ".obsidian").is_dir():
            raise ValueError(f"Missing .obsidian directory: {value}")
        return value

    def skills_check():
        installed = []
        marker = skill_marker()
        for name, env, default in (("Claude Code", "CLAUDE_CONFIG_DIR", "~/.claude"), ("Codex", "CODEX_HOME", "~/.codex")):
            path = Path(os.environ.get(env, default)).expanduser() / "skills/local-video-knowledge/SKILL.md"
            if path.is_file() and marker in path.read_text(encoding="utf-8"):
                installed.append(name)
        if not installed:
            raise ValueError("No managed skill found. Re-run install.sh --all")
        return ", ".join(installed)

    check("Python", python_check)
    check("Bundled ffmpeg", ffmpeg_check)
    check("faster-whisper", lambda: (importlib.import_module("faster_whisper"), version("faster-whisper"))[1])
    check("Whisper model", lambda: model_cached(config.get("whisper_model")))
    check("Obsidian vault", vault_check)
    check("Agent skill", skills_check)
    return {"ok": all(item["ok"] for item in checks), "checks": checks}
