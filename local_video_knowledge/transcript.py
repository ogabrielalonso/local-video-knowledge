"""Audio decoding through bundled ffmpeg and local CPU Whisper transcription."""

import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from .config import atomic_text
from .media import ffmpeg_path


def timestamp(value: float) -> str:
    value = max(0, int(value))
    return f"{value // 3600:02}:{value // 60 % 60:02}:{value % 60:02}"


def decode_audio(media: Path) -> np.ndarray:
    """Decode to mono 16 kHz float32 without invoking PyAV.

    ffmpeg spools s16le to a temporary file under TMPDIR. Convert in 1 MiB
    chunks into one preallocated array, avoiding full-size intermediate copies.
    Three hours need 330 MiB temporary disk and 660 MiB RAM for the returned
    array, plus small conversion buffers. Whisper's model/features are extra.
    """
    with tempfile.TemporaryFile() as pcm:
        try:
            subprocess.run([
                ffmpeg_path(), "-nostdin", "-v", "error", "-i", str(media.resolve()),
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1",
            ], stdout=pcm, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg audio decoding failed: {detail}") from exc
        size = pcm.seek(0, 2)
        if not size or size % 2:
            raise ValueError("ffmpeg produced empty or incomplete PCM audio.")
        audio = np.empty(size // 2, dtype=np.float32)
        pcm.seek(0)
        offset = 0
        while chunk := pcm.read(1024 * 1024):
            samples = np.frombuffer(chunk, dtype="<i2")
            end = offset + samples.size
            np.multiply(samples, 1 / 32768, out=audio[offset:end], dtype=np.float32)
            offset = end
    return audio


def load_model(name: str):
    """Load once per job; the first use downloads the model into the shared cache."""
    from faster_whisper import WhisperModel

    threads = max(1, min(os.cpu_count() or 4, 16))
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)


def transcribe(engine, media: Path, output: Path, language: str | None = None,
               vocabulary: str = "", on_progress=None) -> dict:
    """Write `[HH:MM:SS] text` lines. Returns the detected language and line count.

    The voice-activity filter skips silence, which keeps Whisper from inventing
    text in quiet passages. Vocabulary is passed as a prompt so names and
    uncommon terms are spelled the way the user spells them. A bare word list
    as prompt pushes Whisper into short, looping segments, so it is framed as
    a glossary sentence. Each window is decoded independently of the previous
    text, and consecutive identical segments are dropped, to stop repetition
    loops from spreading. Only the first audio track is transcribed.
    """
    audio = decode_audio(media)
    options = {"language": language, "beam_size": 5, "vad_filter": True,
               "condition_on_previous_text": False}
    if vocabulary.strip():
        options["initial_prompt"] = f"Glossary: {vocabulary.strip().rstrip('.')}."
    segments, info = engine.transcribe(audio, **options)
    lines = []
    previous, previous_end = None, None
    for segment in segments:
        text = segment.text.strip()
        # A loop repeats the same words back to back; a later, separate repeat is kept.
        looped = text.casefold() == previous and segment.start - previous_end < 0.2
        if text and not looped:
            lines.append(f"[{timestamp(segment.start)}] {text}")
        if text:
            previous, previous_end = text.casefold(), segment.end
        if on_progress:
            on_progress(segment.end)
    if not lines:
        raise ValueError("No speech found.")
    atomic_text(output, "\n".join(lines) + "\n")
    return {"language": getattr(info, "language", None) or language, "lines": len(lines)}
