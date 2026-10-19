from local_video_knowledge import config, doctor
from local_video_knowledge.cli import main


def test_doctor_failures_are_independent(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "ffmpeg_path", lambda: "/missing/binary")
    result = doctor.diagnose()
    assert not result["ok"]
    checks = {item["name"]: item for item in result["checks"]}
    assert not checks["Bundled ffmpeg"]["ok"]
    assert not checks["Obsidian vault"]["ok"]
    assert not checks["Agent skill"]["ok"]
    assert checks["Python"]["ok"]
    assert main(["doctor", "--json"]) == 1
    assert '"ok": false' in capsys.readouterr().out


def test_doctor_model_check_never_downloads(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "empty cache"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    config.set_value("whisper_model", "tiny")
    checks = {item["name"]: item for item in doctor.diagnose()["checks"]}
    assert checks["Whisper model"]["ok"]
    assert "not downloaded yet" in checks["Whisper model"]["detail"]
    assert not (tmp_path / "empty cache").exists() or not any((tmp_path / "empty cache").rglob("*.bin"))


def test_doctor_real_dependencies(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config.set_value("vault", str(vault))
    agent = tmp_path / "claude"
    skill = agent / "skills/local-video-knowledge/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"<!-- local-video-knowledge:managed installation-id:{config.home()} -->")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(agent))
    result = doctor.diagnose()
    assert result["ok"], result
    skill.write_text("<!-- local-video-knowledge:managed installation-id:/another/install -->")
    checks = {item["name"]: item for item in doctor.diagnose()["checks"]}
    assert not checks["Agent skill"]["ok"]
