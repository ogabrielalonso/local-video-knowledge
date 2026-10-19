"""User configuration, with an isolated installation home override."""

import json
import os
from pathlib import Path
import tempfile

DEFAULTS = {
    "vault": "",
    "notes_language": "auto",
    "whisper_model": "large-v3-turbo",
    "speech_language": "auto",
    "vocabulary": "",
    "no_dashes": True,
    "tmp_dir": "",
}


def home() -> Path:
    return Path(os.environ.get("LVK_HOME", "~/.local-video-knowledge")).expanduser().absolute()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".lvk-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def load() -> dict:
    path = home() / "config.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a JSON object: {path}")
    result = DEFAULTS | data
    for key in DEFAULTS:
        result[key] = validate(key, result[key])
    return result


def validate(key: str, value):
    if key not in DEFAULTS:
        raise ValueError(f"Unknown config key: {key}. Choose: {', '.join(DEFAULTS)}")
    if key == "no_dashes":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "false"}:
            return str(value).lower() == "true"
        raise ValueError("no_dashes must be true or false")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    if key in {"notes_language", "whisper_model", "speech_language"} and not value.strip():
        raise ValueError(f"{key} must not be empty")
    if key == "vocabulary" and len(value) > 600:
        raise ValueError("vocabulary must be at most 600 characters: list names and terms, not sentences")
    if key in {"vault", "tmp_dir"} and value:
        return str(Path(value).expanduser().absolute())
    return value


def get(key: str):
    if key not in DEFAULTS:
        raise ValueError(f"Unknown config key: {key}")
    return load()[key]


def set_value(key: str, value) -> dict:
    value = validate(key, value)
    data = load()
    data[key] = value
    write_json(home() / "config.json", data)
    return {key: value}


def temporary_root(settings: dict) -> Path:
    return Path(settings["tmp_dir"] or tempfile.gettempdir()).expanduser().absolute()
