"""Bundled ffmpeg: binary selection, media discovery and probing."""

from pathlib import Path
import re
import subprocess

VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".wmv", ".3gp", ".mts", ".m2ts"}
AUDIO = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".aif", ".aiff", ".caf"}
EXTENSIONS = VIDEO | AUDIO
DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
CREATED = re.compile(r"creation_time\s*:\s*(\d{4}-\d{2}-\d{2})")


def ffmpeg_path() -> str:
    import imageio_ffmpeg

    # Ignore IMAGEIO_FFMPEG_EXE overrides: the package binary is deterministic.
    binary_dir = Path(imageio_ffmpeg.__file__).parent / "binaries"
    candidates = sorted(p for p in binary_dir.glob("ffmpeg-*") if p.is_file())
    if not candidates:
        raise RuntimeError("Bundled ffmpeg is missing. Re-run the installer on a supported platform.")
    detected = Path(imageio_ffmpeg.get_ffmpeg_exe())
    return str(detected if detected in candidates else candidates[0])


def natural_key(path: Path) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def discover(target: Path) -> list[Path]:
    """One media file, or every media file under a folder, in natural order.

    Hidden entries and macOS AppleDouble files (._name) are ignored, as are
    symbolic links, so a folder cannot pull in files from elsewhere.
    """
    target = target.expanduser()
    if not target.exists():
        raise ValueError(f"Not found: {target}")
    if target.is_file():
        if target.suffix.lower() not in EXTENSIONS:
            raise ValueError(f"Unsupported file type {target.suffix or '(none)'}. Supported: {', '.join(sorted(EXTENSIONS))}")
        return [target.resolve()]
    found = []
    for path in target.rglob("*"):
        relative = path.relative_to(target)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        found.append(path.resolve())
    if not found:
        raise ValueError(f"No audio or video files found in {target}")
    return sorted(found, key=lambda p: natural_key(p.relative_to(target.resolve())))


def parse_probe(output: str) -> dict:
    if not re.search(r"^Input #0", output, re.M):
        # ffmpeg could not open the file: unreadable, damaged or not media.
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        detail = lines[-1] if lines else "no output"
        return {"duration": None, "has_audio": False, "recorded_date": None,
                "probe_error": f"Could not read this file: {detail}"}
    duration = None
    if match := DURATION.search(output):
        hours, minutes, secs = match.groups()
        duration = round(int(hours) * 3600 + int(minutes) * 60 + float(secs), 2)
    created = CREATED.search(output)
    return {"duration": duration,
            "has_audio": bool(re.search(r"Stream #\d+:\d+.*?: Audio:", output)),
            "recorded_date": created.group(1) if created else None}


def probe(media: Path) -> dict:
    # Without an output file ffmpeg exits nonzero after printing the stream summary.
    result = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(media)],
                            capture_output=True, text=True, errors="replace", timeout=120)
    return parse_probe(result.stderr)
