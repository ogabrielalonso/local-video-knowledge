import json
from pathlib import Path

import pytest

from local_video_knowledge import config, job


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Replace probing and Whisper; keep discovery, workdirs, leases and locks real."""
    calls = []
    facts = {"silent": {"duration": 30.0, "has_audio": True, "recorded_date": None},
             "mute": {"duration": 10.0, "has_audio": False, "recorded_date": None},
             "broken": {"duration": 5.0, "has_audio": True, "recorded_date": None}}

    def probe(path):
        return facts.get(path.stem, {"duration": 60.0, "has_audio": True, "recorded_date": "2024-05-17"})

    def transcribe(engine, media, output, language, vocabulary, on_progress):
        calls.append(media.name)
        if media.stem == "silent":
            raise ValueError("No speech found.")
        if media.stem == "broken":
            raise RuntimeError("ffmpeg audio decoding failed: bad data")
        on_progress(1.0)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"[00:00:00] Words from {media.name}\n")
        return {"language": "en", "lines": 1}

    monkeypatch.setattr(job, "probe", probe)
    monkeypatch.setattr(job, "transcribe", transcribe)
    monkeypatch.setattr(job, "load_model", lambda name: object())
    config.set_value("tmp_dir", str(tmp_path / "work root"))
    return calls


def folder(tmp_path, *names):
    root = tmp_path / "My Clips"
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    return root


def test_folder_job_completes_with_skips_and_errors(tmp_path, fake):
    root = folder(tmp_path, "clip 2.mp4", "clip 10.mp4", "batch/clip 1.mov", "silent.mp3", "mute.mp4",
                  "broken.wav", "readme.txt")
    result = job.start(root, foreground=True)
    assert result["state"] == "complete"
    assert result["files"] == 6 and result["finished"] == 6
    assert result["counts"] == {"done": 3, "no_speech": 1, "no_audio": 1, "error": 1}
    assert result["errors"] == [{"file": "broken.wav", "error": "ffmpeg audio decoding failed: bad data"}]
    assert Path(result["workdir"]).parent == tmp_path / "work root"
    text = Path(result["all_transcripts"]).read_text()
    assert text.index("clip 1.mov") < text.index("clip 2.mp4") < text.index("clip 10.mp4")
    assert "Words from clip 10.mp4" in text
    assert "(Skipped: no speech detected.)" in text and "(Skipped: no audio track.)" in text
    assert "recorded 2024-05-17" in text and "language en" in text
    assert [item["file"] for item in result["transcripts"]] == ["batch/clip 1.mov", "clip 2.mp4", "clip 10.mp4"]
    assert "mute.mp4" not in fake
    assert sorted(p.name for p in root.rglob("*")) == sorted(
        ["batch", "clip 2.mp4", "clip 10.mp4", "clip 1.mov", "silent.mp3", "mute.mp4", "broken.wav", "readme.txt"])


def test_resume_only_transcribes_unfinished_files(tmp_path, fake):
    root = folder(tmp_path, "a.mp4", "b.mp4")
    first = job.start(root, foreground=True)
    assert sorted(fake) == ["a.mp4", "b.mp4"]
    fake.clear()
    (root / "c.mp4").write_bytes(b"new")
    (root / "b.mp4").write_bytes(b"changed content")
    second = job.start(root, foreground=True)
    assert second["workdir"] == first["workdir"]
    assert sorted(fake) == ["b.mp4", "c.mp4"]
    fake.clear()
    third = job.start(root, foreground=True)
    assert fake == [] and third["state"] == "complete"
    # A deleted transcript makes that file pending again.
    transcript = next(Path(third["workdir"], "transcripts").glob("*-a-*.txt"))
    transcript.unlink()
    job.start(root, foreground=True)
    assert fake == ["a.mp4"]


def test_single_file_and_leases(tmp_path, fake):
    clip = folder(tmp_path, "talk.mp4") / "talk.mp4"
    first = job.start(clip, foreground=True)
    second = job.start(clip, foreground=True)
    assert first["kind"] == "file" and first["files"] == 1
    workdir = first["workdir"]
    with pytest.raises(ValueError, match="lease"):
        job.clean(workdir, "f" * 32)
    assert job.clean(workdir, first["lease"]) == {"workdir": workdir, "removed": False, "remaining_leases": 1}
    with pytest.raises(ValueError, match="lease"):
        job.clean(workdir, first["lease"])
    assert job.clean(workdir, second["lease"])["removed"]
    assert not Path(workdir).exists()
    assert clip.exists()


def test_failed_model_load_and_stopped_status(tmp_path, fake, monkeypatch):
    def broken(name):
        raise OSError("no network")

    monkeypatch.setattr(job, "load_model", broken)
    root = folder(tmp_path, "a.mp4")
    result = job.start(root, foreground=True)
    assert result["state"] == "failed"
    assert "Could not load Whisper model large-v3-turbo: no network" in result["error"]
    # A running state without a live worker is reported as stopped, never as running.
    job.update_progress(Path(result["workdir"]), state="running")
    assert job.status(result["workdir"])["state"] == "stopped"


def test_workdir_safety(tmp_path, fake):
    root = folder(tmp_path, "a.mp4")
    with pytest.raises(ValueError, match="must end in lvk_"):
        job.start(root, tmp_path / "elsewhere")
    expected = tmp_path / "custom" / f"lvk_{job.job_id(root)}"
    expected.mkdir(parents=True)
    (expected / "personal.txt").write_text("keep")
    with pytest.raises(ValueError, match="nonempty directory"):
        job.start(root, expected)
    assert (expected / "personal.txt").read_text() == "keep"
    with pytest.raises(ValueError, match="exact workdir"):
        job.status(tmp_path)
    with pytest.raises(ValueError):
        job.clean(str(expected), "a" * 32)
    assert (expected / "personal.txt").exists()


def test_clean_refuses_other_installation(tmp_path, fake, monkeypatch):
    result = job.start(folder(tmp_path, "a.mp4"), foreground=True)
    marker = Path(result["workdir"]) / job.MARKER
    owner = json.loads(marker.read_text())
    marker.write_text(json.dumps(owner | {"installation": "/another/install"}))
    with pytest.raises(ValueError, match="not marked as owned"):
        job.clean(result["workdir"], result["lease"])
    assert Path(result["workdir"]).exists()


def test_background_worker_end_to_end(tmp_path, monkeypatch):
    """Spawn the real detached worker with a stub model package on its path."""
    stub = tmp_path / "stub"
    (stub / "faster_whisper").mkdir(parents=True)
    (stub / "faster_whisper/__init__.py").write_text(
        "from types import SimpleNamespace as N\n"
        "class WhisperModel:\n"
        "    def __init__(self, *a, **k): pass\n"
        "    def transcribe(self, audio, **k):\n"
        "        return iter([N(start=0.0, end=1.0, text='Stub speech')]), N(language='en')\n")
    monkeypatch.setenv("PYTHONPATH", f"{stub}:{Path(job.__file__).parents[1]}")
    config.set_value("tmp_dir", str(tmp_path / "work"))
    root = tmp_path / "clips"
    root.mkdir()
    import subprocess
    from local_video_knowledge.media import ffmpeg_path
    subprocess.run([ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(root / "a.m4a")], check=True)
    started = job.start(root)
    assert started["state"] in {"starting", "loading_model", "running", "complete"}
    finished = job.status(started["workdir"], wait=60)
    assert finished["state"] == "complete", (finished, Path(started["workdir"], "worker.log").read_text())
    assert "Stub speech" in Path(finished["all_transcripts"]).read_text()
    assert job.stop(started["workdir"])["stopped"] is False
    assert job.clean(started["workdir"], started["lease"])["removed"]


def test_new_vocabulary_or_model_redoes_transcripts(tmp_path, fake):
    root = folder(tmp_path, "a.mp4", "mute.mp4", "silent.mp3")
    job.start(root, foreground=True)
    assert sorted(fake) == ["a.mp4", "silent.mp3"]
    fake.clear()
    config.set_value("vocabulary", "Ada Lovelace")
    job.start(root, foreground=True)
    assert sorted(fake) == ["a.mp4", "silent.mp3"]
    fake.clear()
    job.start(root, foreground=True)
    assert fake == []
    config.set_value("whisper_model", "small")
    result = job.start(root, foreground=True)
    assert sorted(fake) == ["a.mp4", "silent.mp3"]
    assert result["counts"] == {"done": 1, "no_audio": 1, "no_speech": 1}


def test_unreadable_file_is_an_error_and_retried(tmp_path, fake, monkeypatch):
    root = folder(tmp_path, "a.mp4", "locked.mp4")
    original = job.probe
    monkeypatch.setattr(job, "probe", lambda path: {"duration": None, "has_audio": False, "recorded_date": None,
                                                    "probe_error": "Could not read this file: denied"}
                        if path.stem == "locked" else original(path))
    result = job.start(root, foreground=True)
    assert result["counts"] == {"done": 1, "error": 1}
    assert result["errors"] == [{"file": "locked.mp4", "error": "Could not read this file: denied"}]
    monkeypatch.setattr(job, "probe", original)
    fake.clear()
    assert job.start(root, foreground=True)["counts"] == {"done": 2}
    assert fake == ["locked.mp4"]


def test_installations_do_not_share_workdirs(tmp_path, monkeypatch):
    target = tmp_path / "a.mp4"
    target.write_bytes(b"x")
    first = job.job_id(target)
    monkeypatch.setenv("LVK_HOME", str(tmp_path / "other install"))
    assert job.job_id(target) != first


def test_running_job_with_other_settings_is_refused(tmp_path, fake, monkeypatch):
    root = folder(tmp_path, "a.mp4")
    result = job.start(root, foreground=True)
    workdir = Path(result["workdir"])
    # A worker spawned moments ago counts as running, for start and for clean.
    job.update_progress(workdir, state="starting", started=__import__("time").time(), settings="other")
    with pytest.raises(ValueError, match="other settings"):
        job.start(root)
    with pytest.raises(ValueError, match="still running"):
        job.clean(str(workdir), result["lease"])
    job.update_progress(workdir, settings=job.settings_key(config.load()))
    again = job.start(root)
    assert again["lease"] != result["lease"]


def test_worker_uses_settings_recorded_at_start(tmp_path, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(job, "load_model", lambda name: seen.append(name) or object())
    root = folder(tmp_path, "a.mp4")
    monkeypatch.setattr(job, "spawn", lambda workdir: None)
    started = job.start(root)
    workdir = Path(started["workdir"])
    config.set_value("whisper_model", "small")
    job.run_worker(workdir)
    assert seen == ["large-v3-turbo"]
