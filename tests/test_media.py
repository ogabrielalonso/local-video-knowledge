from pathlib import Path

import pytest

from local_video_knowledge.media import discover, parse_probe

PROBE = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'clip.mp4':
  Metadata:
    creation_time   : 2024-05-17T09:12:44.000000Z
  Duration: 01:02:03.45, start: 0.000000, bitrate: 1205 kb/s
  Stream #0:0[0x1](und): Video: h264 (avc1 / 0x31637661), yuv420p, 1280x720
  Stream #0:1[0x2](eng): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo
"""


def test_parse_probe():
    assert parse_probe(PROBE) == {"duration": 3723.45, "has_audio": True, "recorded_date": "2024-05-17"}


def test_parse_probe_video_only_and_unknown():
    video_only = PROBE.replace("  Stream #0:1[0x2](eng): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo\n", "")
    assert parse_probe(video_only)["has_audio"] is False
    assert parse_probe("garbage")["probe_error"] == "Could not read this file: garbage"


def test_parse_probe_unreadable():
    facts = parse_probe("clip.mp4: Permission denied\n")
    assert facts["probe_error"] == "Could not read this file: clip.mp4: Permission denied"
    assert facts["has_audio"] is False


def test_discover_folder(tmp_path):
    for name in ["clip 10.mp4", "clip 2.MOV", "clip 1.mp3", "notes.txt", ".hidden.wav", "._clip 3.mp4",
                 ".cache/inner.mp4", "sub/clip 1.m4a"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    (tmp_path / "linked.mp4").symlink_to(tmp_path / "clip 1.mp3")
    found = [str(p.relative_to(tmp_path)) for p in discover(tmp_path)]
    assert found == ["clip 1.mp3", "clip 2.MOV", "clip 10.mp4", "sub/clip 1.m4a"]


def test_discover_file_and_errors(tmp_path):
    clip = tmp_path / "talk.webm"
    clip.write_bytes(b"x")
    assert discover(clip) == [clip.resolve()]
    (tmp_path / "doc.pdf").write_bytes(b"x")
    with pytest.raises(ValueError, match="Unsupported"):
        discover(tmp_path / "doc.pdf")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No audio or video"):
        discover(empty)
    with pytest.raises(ValueError, match="Not found"):
        discover(tmp_path / "missing")
