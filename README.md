<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-236637" alt="License: PolyForm Noncommercial 1.0.0"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-526256" alt="Version 0.1.0">
  <a href="tests/"><img src="https://img.shields.io/badge/tests-113%20passing-236637" alt="113 tests passing"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-17271d" alt="Python 3.12 or newer">
  <img src="https://img.shields.io/badge/agents-Claude%20Code%20%2B%20Codex-526256" alt="Works with Claude Code and Codex">
</p>

<h1 align="center">local-video-knowledge</h1>

<p align="center">
  Turn the recordings on your computer into knowledge in your second brain.<br>
  Point Claude Code or Codex at a video, a podcast or a folder of clips. It transcribes them locally,
  reads every word, then writes connected notes your AI can use in future sessions.
</p>

<p align="center">
  <a href="#get-started">Get started</a> ·
  <a href="#for-engineers">For engineers</a> ·
  <a href="#license">License</a>
</p>

## Your recordings, uploaded

Talks you gave, podcast episodes, interviews, short clips for social media, voice memos: a lot of
what you know is locked inside recordings on your disk. This skill opens them. Your agent
transcribes every file on your own computer, studies the complete transcripts, and files what
matters as connected notes in your Obsidian vault. Because your AI reads that vault as context,
your next sessions start with that knowledge.

It is the sibling of [youtube-knowledge](https://github.com/ogabrielalonso/youtube-knowledge),
which does the same for YouTube links.

## Private by design

Transcription runs on your computer's processor with an open Whisper model. No recording, audio
or transcript is uploaded to a transcription service. Your agent (Claude Code or Codex) reads the
transcripts to write the notes, as it reads any other file you share with it.

## Requirements

- **A second brain:** an Obsidian vault (the folder where your notes live) that Claude Code or
  Codex already uses as context.
- **An agent:** [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), or both, on your own subscription.
  No separate paid API key.
- **A computer:** macOS or Linux with `curl`. The installer brings everything else (no sudo).
  About 3 GB of free disk for the program and the default model. An Apple Silicon Mac with 16 GB
  of memory or more is comfortable; 8 GB works with a smaller model (see Configuration).

## What it does

1. **Finds the recordings.** One file, or every audio and video file in a folder and its
   subfolders, in natural order (clip 2 before clip 10). Hidden files and documents are ignored.
2. **Transcribes locally, in the background.** A long podcast or a hundred clips never block your
   agent. The agent checks progress and waits. If the computer sleeps or the job stops, running it
   again resumes where it ended: finished files are kept.
3. **Reads everything, then writes.** The agent first establishes who is speaking (you, someone
   else, or a conversation), reads every transcript in full, and only then writes an overview note
   and a few deep insight notes, linked both ways to your existing notes on the same topics.
4. **Follows your vault's rules.** If your vault says new material goes to an inbox as drafts, or
   in a given language, the agent does that.
5. **Checks and cleans up.** The notes are validated (required fields, links that resolve, a
   minimum depth that scales with the length of the recording). The temporary transcription files
   are removed after success. Your recordings are never moved, renamed or changed.

The skill reads speech only. It does not look at the picture. It transcribes the first audio track
of each file, and the transcript does not label who is speaking: in a conversation, the agent
attributes a passage to a person only when the words make it clear.

## Get started

### 1. Run the installer in your terminal

On macOS or Linux, no sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/ogabrielalonso/local-video-knowledge/main/install.sh | bash
```

It installs Python 3.12, CPU Whisper and a bundled ffmpeg into `~/.local-video-knowledge`, and
asks for your Obsidian vault folder. The Whisper model (`large-v3-turbo`, about 1.6 GB) downloads
on the first transcription.

### 2. The skill is added to your agents

| Agent | Default skill folder |
| --- | --- |
| Claude Code | `~/.claude/skills/local-video-knowledge/` |
| Codex | `~/.codex/skills/local-video-knowledge/` |

The installer detects which agents you have. Use `--claude` or `--codex` to choose, or `--all`
for both. Custom `CLAUDE_CONFIG_DIR` and `CODEX_HOME` values override the default roots.

### 3. Open a new session

Start a **new** Claude Code or Codex session so it loads the installed skill, ideally in your
vault folder.

### 4. Give it a file or a folder

In the **Claude Code chat**:

```text
/local-video-knowledge "/Users/you/Movies/My talks"
```

In the **Codex chat**:

```text
$local-video-knowledge "/Users/you/Movies/My talks"
```

Or just ask: "add the clips in my Movies/My talks folder to my second brain". If it is not obvious
from the folder name, the agent asks whether the speaker is you.

**Check it:**

```bash
lvk doctor
```

If your shell says `lvk: command not found`, run `~/.local-video-knowledge/bin/lvk doctor` instead
(or add `~/.local/bin` to your PATH). The skill itself already knows the full path.

**Uninstall, from a clone:**

```bash
git clone https://github.com/ogabrielalonso/local-video-knowledge.git
bash local-video-knowledge/uninstall.sh
```

Uninstall preserves your recordings, vault notes, work directories, backups and the shared model cache.

## How long it takes

Speed depends on the computer. Measured with the default `large-v3-turbo` model on a MacBook with
an Apple M4 and 16 GB of memory, transcription runs about four times faster than real time: a
5 minute 41 second recording took 85 seconds. A one hour podcast takes about 15 minutes. The first
run also downloads the model (about 1.6 GB). The agent reports progress and an estimate while it
waits, and your computer stays usable meanwhile. Heavy use at the same time (a video call, many
browser tabs) slows it down: the same recording took about four and a half minutes during a call.

## Configuration

Installer flags (from a clone or after `bash -s --` with the piped installer):

| Flag | Effect |
| --- | --- |
| `--claude` / `--codex` / `--all` | Choose which agents receive the skill. |
| `--vault PATH` | Set the Obsidian vault folder. |
| `--notes-language LANG` | Set the language of generated notes. |
| `--whisper-model MODEL` | Choose and download a Whisper model at install time. |
| `--yes` | Use non-interactive defaults without editing shell startup files. |

Settings can be changed at any time:

```bash
lvk config get --json
lvk config set vault "/path/to/Obsidian vault"
lvk config set notes_language auto
lvk config set speech_language auto
lvk config set whisper_model large-v3-turbo
lvk config set vocabulary "Ada Lovelace, Fernweh Labs, Kubernetes"
lvk config set no_dashes true
lvk config set tmp_dir "/path/to/temporary directory"
```

| Key | Meaning |
| --- | --- |
| `vault` | Obsidian vault containing `.obsidian/`. |
| `notes_language` | `auto` writes notes in the spoken language; or set a language such as `en`. |
| `speech_language` | `auto` detects the spoken language per file; set it (for example `en` or `pt`) if detection is wrong. |
| `whisper_model` | `large-v3-turbo` (default, best balance), `medium`, `small` or `base` for older or 8 GB machines. |
| `vocabulary` | Names and uncommon terms, comma separated (up to 600 characters), so they are spelled your way. |
| `no_dashes` | Reject en and em dashes in notes; enabled by default. |
| `tmp_dir` | Root for temporary transcription work directories. |

## Troubleshooting

Run `lvk doctor` to check Python, the bundled ffmpeg, Whisper, the model download, your vault and
the installed agent skills. If a name keeps coming out wrong, add it to `vocabulary` and run the
skill again on the same file. If a file is reported as an error, it is probably damaged or in an
unusual format; the rest of the folder is still transcribed. Keep the reported work directory if
the analysis stops before validation: running the skill again resumes from it.

---

## For engineers

`lvk` handles deterministic transcription, validation and cleanup. The agent reads and interprets
the complete transcripts, searches the vault, then writes the notes. The CLI does not write or
interpret notes by itself.

```bash
lvk transcribe "FILE_OR_FOLDER" --json        # starts or resumes a detached worker; returns workdir and lease
lvk status "WORKDIR" --wait 100 --json        # waits up to the given seconds (at most 540)
lvk stop "WORKDIR"                             # stops the worker; finished files are kept
lvk check "NOTE_PATH" ... --vault "VAULT_PATH" --json
lvk clean "WORKDIR" --lease "LEASE" --json
lvk doctor
lvk config get --json
```

`transcribe` probes every file with the bundled ffmpeg, writes a manifest, and hands the work to a
detached worker that holds an exclusive lock for its lifetime, so `status` can tell a live job
from a dead one. Each file is cached by its relative path, size and modification time; a rerun
transcribes only new, changed or unfinished files. Transcription uses faster-whisper on the CPU
with int8 weights, voice activity detection (silence is skipped, which prevents invented text),
independent decoding windows and removal of consecutive duplicate segments. The vocabulary is
passed as a glossary prompt. When the job completes, `all-transcripts.md` holds every transcript
with timestamps, durations, recording dates when the file has one, and detected languages.

Every `transcribe` creates a fresh lease. `clean` releases that lease and removes the work
directory only after its last lease is released, and only if the directory carries this
installation's ownership marker. `check` parses Markdown and validates required metadata, the
minimum number of non-blank lines (scaled by recording length: under 5 minutes, under 15 minutes,
longer), forbidden dashes when configured, and wikilink targets. It cannot establish factual
accuracy or usefulness; the agent reviews the content.

The package is in `local_video_knowledge/`: `job.py`, `transcript.py`, `media.py`, `check.py`,
`config.py`, `doctor.py` and `cli.py`. The agent method is in [SKILL.md](SKILL.md). Dependency pins
are in [constraints.txt](constraints.txt). The local test run on 2026-10-19 passed **113 tests**.
The supported systems are macOS and Linux.

## License

[PolyForm Noncommercial 1.0.0](LICENSE): free for personal and non-commercial use. Commercial
use requires a separate license.

<p align="center">
  <br>
  Made by <b>Gabriel Alonso</b><br>
  <a href="https://github.com/ogabrielalonso">GitHub</a> · <a href="https://www.linkedin.com/in/ogabrielalonso/">LinkedIn</a>
</p>
