import pytest

from local_video_knowledge import config


def test_roundtrip(tmp_path):
    assert config.get("notes_language") == "auto"
    assert config.get("whisper_model") == "large-v3-turbo"
    assert config.get("no_dashes") is True
    config.set_value("vault", str(tmp_path / "notes with spaces"))
    config.set_value("no_dashes", "false")
    config.set_value("vocabulary", "Ada Lovelace, Fernweh Labs")
    assert config.get("vault") == str(tmp_path / "notes with spaces")
    assert config.get("no_dashes") is False
    assert config.get("vocabulary") == "Ada Lovelace, Fernweh Labs"


@pytest.mark.parametrize("key,value", [("unknown", "x"), ("no_dashes", "maybe"), ("notes_language", ""),
                                       ("whisper_model", " "), ("vocabulary", "x" * 601)])
def test_invalid(key, value):
    with pytest.raises(ValueError):
        config.set_value(key, value)


def test_temporary_root(tmp_path):
    config.set_value("tmp_dir", str(tmp_path / "work"))
    assert config.temporary_root(config.load()) == tmp_path / "work"
