"""Resumable background transcription of one file or one folder.

`start` scans and probes the media, then hands the work to a detached worker so
long recordings never depend on an agent's command timeout. The worker holds an
exclusive job lock for its whole life: a free lock means no worker is running.
Every finished file is kept, so a stopped job resumes where it ended.
"""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

from . import config
from .media import discover, probe
from .transcript import load_model, timestamp, transcribe

MARKER = ".local-video-knowledge.json"
JOB_NAME = re.compile(r"lvk_[0-9a-f]{12}\Z")
FINAL = {"done", "no_speech", "no_audio"}
MAX_WAIT = 540


def job_id(target: Path) -> str:
    # Two installations never share a workdir, even for the same recording.
    key = f"{target.resolve()}|{config.home().resolve()}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def file_key(path: Path, relative: str) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{relative}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:10]


def settings_key(settings: dict) -> str:
    """Transcripts made with another model, language or vocabulary are redone."""
    parts = (settings["whisper_model"], settings["speech_language"], settings["vocabulary"].strip())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


def slug(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", Path(text).stem).strip("-").lower()
    return value[:40].strip("-") or "media"


def lock_path(workdir: Path, kind: str) -> Path:
    root = config.home() / "state" / "locks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{hashlib.sha256(str(workdir).encode()).hexdigest()}.{kind}.lock"


@contextmanager
def work_lock(workdir: Path):
    """Serialize setup, lease and cleanup changes; never held during transcription."""
    with lock_path(workdir, "work").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"Workdir {workdir} is in use by another lvk command.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def worker_running(workdir: Path) -> bool:
    with lock_path(workdir, "job").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
        return False


def busy(workdir: Path) -> bool:
    """A worker holds the job lock, or was spawned moments ago and is taking it."""
    if worker_running(workdir):
        return True
    progress = read_json(workdir / "progress.json", {}) or {}
    return progress.get("state") == "starting" and time.time() - progress.get("started", 0) <= 30


def ownership(target: Path) -> dict:
    return {"target": str(target), "installation": str(config.home().resolve())}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def resolve_workdir(target: Path, workdir: Path | None) -> Path:
    expected = f"lvk_{job_id(target)}"
    root = config.temporary_root(config.load())
    workdir = workdir.expanduser().absolute() if workdir else root / expected
    if workdir.name != expected:
        raise ValueError(f"--workdir must end in {expected}, so cleanup can target it safely.")
    if workdir.is_symlink():
        raise ValueError("The workdir must not be a symbolic link.")
    return workdir.resolve()


def build_manifest(target: Path, workdir: Path) -> dict:
    files = discover(target)
    base = target.resolve() if target.is_dir() else target.resolve().parent
    previous = {item["key"]: item for item in (read_json(workdir / "manifest.json", {}) or {}).get("files", [])}
    items = []
    for index, path in enumerate(files, 1):
        relative = str(path.relative_to(base))
        key = file_key(path, relative)
        known = previous.get(key)
        if known and not known.get("probe_error"):
            facts = {k: known[k] for k in ("duration", "has_audio", "recorded_date")}
        else:
            facts = probe(path)
        items.append({"index": index, "path": str(path), "relative": relative, "key": key,
                      "transcript": f"transcripts/{index:03}-{slug(relative)}-{key}.txt", **facts})
    total = sum(item["duration"] or 0 for item in items)
    manifest = {"target": str(target.resolve()), "kind": "folder" if target.is_dir() else "file",
                "files": items, "total_duration": round(total, 2)}
    config.write_json(workdir / "manifest.json", manifest)
    return manifest


def pending(manifest: dict, results: dict, workdir: Path, settings: str) -> list[dict]:
    left = []
    for item in manifest["files"]:
        result = results.get(item["key"], {})
        complete = result.get("status") in FINAL
        if result.get("status") == "done" and not (workdir / item["transcript"]).is_file():
            complete = False
        if result.get("status") in {"done", "no_speech"} and result.get("settings") != settings:
            complete = False
        if not complete:
            left.append(item)
    return left


def update_progress(workdir: Path, **changes) -> dict:
    progress = read_json(workdir / "progress.json", {}) or {}
    progress.update(changes)
    config.write_json(workdir / "progress.json", progress)
    return progress


def start(target: Path, workdir: Path | None = None, foreground: bool = False) -> dict:
    target = target.expanduser()
    if not target.exists():
        raise ValueError(f"Not found: {target}")
    target = target.resolve()
    workdir = resolve_workdir(target, workdir)
    with work_lock(workdir):
        if workdir.exists() and not (workdir / MARKER).exists() and any(workdir.iterdir()):
            raise ValueError("Refusing to use a nonempty directory not created by lvk.")
        workdir.mkdir(parents=True, exist_ok=True)
        marker = workdir / MARKER
        if marker.exists() and read_json(marker) != ownership(target):
            raise ValueError("Workdir ownership marker is invalid or belongs to another installation.")
        config.write_json(marker, ownership(target))
        leases = workdir / "leases"
        if leases.is_symlink():
            raise ValueError("The leases directory must not be a symbolic link.")
        leases.mkdir(exist_ok=True)
        running = busy(workdir)
        left = []
        settings = config.load()
        fingerprint = settings_key(settings)
        if running:
            current = (read_json(workdir / "progress.json", {}) or {}).get("settings")
            if current and current != fingerprint:
                raise ValueError("This path is being transcribed with other settings (model, language or "
                                 "vocabulary). Wait for it, or run lvk stop, then run lvk transcribe again.")
        else:
            manifest = build_manifest(target, workdir)
            progress = read_json(workdir / "progress.json", {}) or {}
            results = progress.get("results", {})
            left = pending(manifest, results, workdir, fingerprint)
            if not left:
                finalize(workdir, manifest, results)
            else:
                # Forget the previous worker's PID so stop can never signal a reused one.
                update_progress(workdir, state="starting", error=None, results=results, pid=None,
                                settings=fingerprint, config=settings, total=len(manifest["files"]),
                                started=time.time())
                if not foreground:
                    spawn(workdir)
        lease = uuid.uuid4().hex
        (leases / lease).touch(exist_ok=False)
    if foreground and not running and left:
        run_worker(workdir)
    return status(workdir) | {"lease": lease}


def spawn(workdir: Path) -> None:
    log = (workdir / "worker.log").open("a", encoding="utf-8")
    env = os.environ | {"LVK_HOME": str(config.home())}
    subprocess.Popen([sys.executable, "-m", "local_video_knowledge.job", str(workdir)],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env,
                     start_new_session=True, close_fds=True)
    log.close()


def run_worker(workdir: Path) -> int:
    stream = lock_path(workdir, "job").open("a")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0  # Another worker owns this job.

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    progress = read_json(workdir / "progress.json", {}) or {}
    results = progress.get("results", {})
    try:
        # Use the settings recorded when the job started, so its fingerprint stays true.
        settings = progress.get("config") or config.load()
        manifest = read_json(workdir / "manifest.json")
        fingerprint = settings_key(settings)
        left = pending(manifest, results, workdir, fingerprint)
        update_progress(workdir, state="loading_model", pid=os.getpid(), model=settings["whisper_model"],
                        heartbeat=time.time(), current=None, error=None)
        try:
            engine = load_model(settings["whisper_model"])
        except Exception as exc:
            update_progress(workdir, state="failed", error=f"Could not load Whisper model {settings['whisper_model']}: {exc}")
            return 1
        language = None if settings["speech_language"] == "auto" else settings["speech_language"]
        run_started, audio_done = time.time(), 0.0
        update_progress(workdir, state="running", run_started=run_started, audio_done=0.0,
                        audio_left=sum(item["duration"] or 0 for item in left))
        for item in left:
            last = [0.0]

            def tick(position, item=item):
                now = time.time()
                if now - last[0] >= 2:
                    last[0] = now
                    update_progress(workdir, heartbeat=now, current=item["relative"], position=round(position, 1),
                                    audio_done=round(audio_done + position, 1))

            tick(0.0)
            if item.get("probe_error"):
                results[item["key"]] = {"status": "error", "error": item["probe_error"]}
            elif not item["has_audio"]:
                results[item["key"]] = {"status": "no_audio", "settings": fingerprint}
            else:
                try:
                    found = transcribe(engine, Path(item["path"]), workdir / item["transcript"],
                                       language, settings["vocabulary"], tick)
                    results[item["key"]] = {"status": "done", "settings": fingerprint} | found
                except ValueError as exc:
                    if "No speech" in str(exc):
                        results[item["key"]] = {"status": "no_speech", "settings": fingerprint}
                    else:
                        results[item["key"]] = {"status": "error", "error": str(exc)}
                except Exception as exc:
                    results[item["key"]] = {"status": "error", "error": str(exc)}
            audio_done += item["duration"] or 0
            update_progress(workdir, results=results, heartbeat=time.time(), audio_done=round(audio_done, 1))
        finalize(workdir, manifest, results)
        return 0
    except KeyboardInterrupt:
        update_progress(workdir, state="stopped", results=results, error="Stopped before the end. Finished files are kept.")
        return 130
    except Exception as exc:
        update_progress(workdir, state="failed", results=results, error=str(exc))
        return 1
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def clock(seconds) -> str:
    return timestamp(seconds or 0)


def finalize(workdir: Path, manifest: dict, results: dict) -> None:
    title = Path(manifest["target"]).name
    lines = [f"# Transcripts: {title}", "",
             f"Source: `{manifest['target']}` ({manifest['kind']}, {len(manifest['files'])} files, "
             f"total {clock(manifest['total_duration'])})", ""]
    for item in manifest["files"]:
        result = results.get(item["key"], {})
        facts = [f"duration {clock(item['duration'])}"]
        if item["recorded_date"]:
            facts.append(f"recorded {item['recorded_date']}")
        if result.get("language"):
            facts.append(f"language {result['language']}")
        lines += [f"## {item['index']}. {item['relative']}", "", f"_{', '.join(facts)}_", ""]
        if result.get("status") == "done":
            lines += (workdir / item["transcript"]).read_text(encoding="utf-8").rstrip("\n").splitlines()
        else:
            reason = {"no_speech": "no speech detected", "no_audio": "no audio track"}.get(
                result.get("status"), f"not transcribed: {result.get('error', 'unknown error')}")
            lines.append(f"(Skipped: {reason}.)")
        lines.append("")
    config.atomic_text(workdir / "all-transcripts.md", "\n".join(lines))
    update_progress(workdir, state="complete", results=results, current=None, finished=time.time(),
                    total=len(manifest["files"]))


def status(workdir: Path, wait: float = 0) -> dict:
    workdir = Path(workdir).expanduser().absolute()
    if not JOB_NAME.fullmatch(workdir.name) or not (workdir / MARKER).is_file():
        raise ValueError("Expected the exact workdir returned by lvk transcribe.")
    deadline = time.time() + max(0.0, min(float(wait), MAX_WAIT))
    while True:
        progress = read_json(workdir / "progress.json", {}) or {}
        state = progress.get("state", "unknown")
        if state in {"starting", "loading_model", "running"} and not worker_running(workdir):
            # A spawned worker may need a moment to take its lock.
            if state != "starting" or time.time() - progress.get("started", 0) > 30:
                state = "stopped"
        if state not in {"starting", "loading_model", "running"} or time.time() >= deadline:
            break
        time.sleep(2)
    manifest = read_json(workdir / "manifest.json", {}) or {}
    files = manifest.get("files", [])
    results = progress.get("results", {})
    counts = {}
    for item in files:
        kind = results.get(item["key"], {}).get("status", "pending")
        counts[kind] = counts.get(kind, 0) + 1
    finished = sum(counts.get(kind, 0) for kind in FINAL | {"error"})
    eta = None
    if state == "running" and progress.get("run_started"):
        elapsed = time.time() - progress["run_started"]
        done, left = progress.get("audio_done", 0), progress.get("audio_left", 0)
        if done > 5 and elapsed > 5:
            eta = round(max(0.0, left - done) * elapsed / done)
    result = {"workdir": str(workdir), "state": state, "target": manifest.get("target"),
              "kind": manifest.get("kind"), "files": len(files), "finished": finished, "counts": counts,
              "total_duration": manifest.get("total_duration"), "model": progress.get("model"),
              "current": progress.get("current") if state == "running" else None, "eta_seconds": eta,
              "errors": [{"file": item["relative"], "error": results[item["key"]].get("error")}
                         for item in files if results.get(item["key"], {}).get("status") == "error"]}
    if state == "complete":
        result["all_transcripts"] = str(workdir / "all-transcripts.md")
        result["transcripts"] = [{"file": item["relative"], "path": str(workdir / item["transcript"]),
                                  "duration": item["duration"], "recorded_date": item["recorded_date"],
                                  "language": results.get(item["key"], {}).get("language")}
                                 for item in files if results.get(item["key"], {}).get("status") == "done"]
    if progress.get("error") and state in {"failed", "stopped"}:
        result["error"] = progress["error"]
    if state == "stopped" and "error" not in result:
        result["error"] = "The worker is not running. Run lvk transcribe on the same path to resume."
    return result


def stop(workdir: Path) -> dict:
    workdir = Path(workdir).expanduser().absolute()
    if not JOB_NAME.fullmatch(workdir.name) or not (workdir / MARKER).is_file():
        raise ValueError("Expected the exact workdir returned by lvk transcribe.")
    if not worker_running(workdir):
        return {"workdir": str(workdir), "stopped": False, "detail": "No worker is running."}
    pid = (read_json(workdir / "progress.json", {}) or {}).get("pid")
    if not pid:
        return {"workdir": str(workdir), "stopped": False, "detail": "No worker is running."}
    os.kill(int(pid), signal.SIGTERM)
    for _ in range(30):
        if not worker_running(workdir):
            break
        time.sleep(1)
    return {"workdir": str(workdir), "stopped": not worker_running(workdir)}


def clean(workdir: str, lease: str) -> dict:
    target = Path(workdir).expanduser()
    if not target.is_absolute() or not JOB_NAME.fullmatch(target.name):
        raise ValueError("Expected the exact absolute workdir returned by transcribe and its lease.")
    if target.is_symlink():
        raise ValueError("Unsafe cleanup target. No files were deleted.")
    if not re.fullmatch(r"[0-9a-f]{32}", lease):
        raise ValueError("Invalid or unknown lease. No files were deleted.")
    target = target.resolve()
    with work_lock(target):
        owner = read_json(target / MARKER) if (target / MARKER).is_file() else {}
        if not owner or owner.get("installation") != str(config.home().resolve()) or \
                f"lvk_{job_id(Path(owner['target']))}" != target.name:
            raise ValueError("Directory is not marked as owned by this installation. No files were deleted.")
        if busy(target):
            raise ValueError("Transcription is still running. Wait for it or run lvk stop first. No files were deleted.")
        leases = target / "leases"
        token = leases / lease
        if leases.is_symlink() or token.is_symlink() or not token.is_file():
            raise ValueError("Stale or unknown lease. No files were deleted.")
        token.unlink()
        remaining = sum(1 for _ in leases.iterdir())
        if remaining == 0:
            shutil.rmtree(target)
    return {"workdir": str(target), "removed": remaining == 0, "remaining_leases": remaining}


if __name__ == "__main__":
    raise SystemExit(run_worker(Path(sys.argv[1])))
