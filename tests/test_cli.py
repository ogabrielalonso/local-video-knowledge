import json

import pytest

from local_video_knowledge.cli import main


def test_json_on_either_side(capsys):
    assert main(["--json", "config", "get", "whisper_model"]) == 0
    assert json.loads(capsys.readouterr().out) == {"whisper_model": "large-v3-turbo"}
    assert main(["config", "get", "no_dashes", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"no_dashes": True}


def test_json_failure(capsys):
    assert main(["clean", "../../", "--lease", "a" * 32, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_transcribe_missing_path(tmp_path, capsys):
    assert main(["transcribe", str(tmp_path / "missing"), "--json"]) == 1
    assert "Not found" in json.loads(capsys.readouterr().out)["error"]


def test_status_rejects_foreign_directory(tmp_path, capsys):
    assert main(["status", str(tmp_path), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_check_nonzero(tmp_path, capsys):
    path = tmp_path / "bad.md"
    path.write_text("Broken [[missing]]")
    assert main(["check", str(path), "--vault", str(tmp_path), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["files"][0]["ok"] is False


def test_clean_requires_lease(capsys):
    with pytest.raises(SystemExit) as error:
        main(["clean", "lvk_000000000000"])
    assert error.value.code == 2
    assert "--lease" in capsys.readouterr().err
