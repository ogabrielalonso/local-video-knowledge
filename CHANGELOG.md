# Changelog

## 0.1.0 (2026-10-19)

First release.

- `lvk transcribe` turns one recording or a whole folder into timestamped transcripts on the local CPU with faster-whisper (`large-v3-turbo` by default). It runs in a detached background worker, and `lvk status --wait` follows it, so long recordings never depend on an agent's command timeout.
- Finished files are kept. Running `lvk transcribe` again on the same path resumes and transcribes only new, changed or unfinished files.
- Files without an audio track or without speech are reported and skipped. A broken file is recorded as an error and the rest of the folder continues.
- An optional vocabulary (names and uncommon terms) guides spelling. Changing the model, speech language or vocabulary transcribes finished files again on the next run.
- `lvk check` validates the notes the agent writes. Minimum lengths scale with the recording's duration, and `status: draft` is accepted for vaults that keep new material in an inbox.
- The installer sets up an isolated Python 3.12 environment with pinned dependencies and bundled ffmpeg, and installs the skill for Claude Code and Codex. The uninstaller removes only what the installer recorded.
