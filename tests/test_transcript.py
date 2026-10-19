import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from local_video_knowledge.media import ffmpeg_path, probe
from local_video_knowledge.transcript import decode_audio, timestamp, transcribe


class Engine:
    def __init__(self, texts):
        self.texts, self.options = texts, None

    def transcribe(self, audio, **options):
        self.options = options
        segments = (SimpleNamespace(start=i * 5.0, end=i * 5.0 + 5, text=text) for i, text in enumerate(self.texts))
        return segments, SimpleNamespace(language="en")


@pytest.fixture
def tone(tmp_path):
    path = tmp_path / "tone with spaces.m4a"
    subprocess.run([ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-metadata", "creation_time=2024-05-17T10:00:00Z", str(path)], check=True)
    return path


def test_timestamp():
    assert timestamp(3723.9) == "01:02:03"
    assert timestamp(-1) == "00:00:00"


def test_decode_and_probe_real_ffmpeg(tone):
    audio = decode_audio(tone)
    assert audio.dtype == np.float32 and 31000 < audio.size < 33000
    assert float(np.abs(audio).max()) <= 1.0
    facts = probe(tone)
    assert facts["has_audio"] and 1.9 < facts["duration"] < 2.2
    assert facts["recorded_date"] == "2024-05-17"


def test_transcribe_drops_repeats_and_frames_vocabulary(tone, tmp_path):
    engine = Engine([" Hello there.", "Claimed", "claimed ", "  ", "Bye."])
    output = tmp_path / "out" / "t.txt"
    seen = []
    result = transcribe(engine, tone, output, None, "Ada Lovelace, Fernweh Labs.", seen.append)
    assert output.read_text() == "[00:00:00] Hello there.\n[00:00:05] Claimed\n[00:00:20] Bye.\n"
    assert result == {"language": "en", "lines": 3}
    assert engine.options["initial_prompt"] == "Glossary: Ada Lovelace, Fernweh Labs."
    assert engine.options["condition_on_previous_text"] is False
    assert engine.options["vad_filter"] is True
    assert seen == [5.0, 10.0, 15.0, 20.0, 25.0]


def test_separate_repeats_are_kept(tone, tmp_path):
    class Gapped(Engine):
        def transcribe(self, audio, **options):
            segments = [SimpleNamespace(start=0.0, end=1.0, text="Yes."), SimpleNamespace(start=4.0, end=5.0, text="Yes.")]
            return iter(segments), SimpleNamespace(language="en")

    transcribe(Gapped([]), tone, tmp_path / "t.txt")
    assert (tmp_path / "t.txt").read_text() == "[00:00:00] Yes.\n[00:00:04] Yes.\n"


def test_transcribe_without_vocabulary_or_speech(tone, tmp_path):
    engine = Engine(["Only line."])
    transcribe(engine, tone, tmp_path / "a.txt")
    assert "initial_prompt" not in engine.options
    with pytest.raises(ValueError, match="No speech"):
        transcribe(Engine(["", " "]), tone, tmp_path / "b.txt")
    assert not (tmp_path / "b.txt").exists()


def test_decode_failure_is_reported(tmp_path):
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not audio")
    with pytest.raises(RuntimeError, match="ffmpeg audio decoding failed"):
        decode_audio(broken)
