---
name: local-video-knowledge
description: Transcribe local video or audio recordings (one file or a whole folder) on this computer with a local Whisper model, analyze every transcript in full, and create substantial topic-routed Obsidian MOC and insight notes with validated bidirectional links. Use when a user asks to learn from, document, or add to their second brain recordings stored on their own disk, such as talks, clips, podcasts, interviews or voice memos.
---
<!-- local-video-knowledge:managed -->

# Local Video Knowledge

Turn recordings on this computer into substantial, interconnected knowledge. The
method is complete analysis before writing, whether the input is one clip, a long
podcast or a folder of a hundred short videos. Transcription runs locally: no
recording leaves the machine. The CLI handles transcription and checks; you
perform the analysis and write the notes. This skill reads speech only. It does
not look at the picture.

## Resolve the request

Input in Claude Code: `/local-video-knowledge <file or folder> [vault]`.
Input in Codex: `$local-video-knowledge <file or folder> [vault]`, or ask in natural language.

Before running CLI commands, use `lvk` if it is available on PATH. Otherwise use
the installed wrapper below, or `~/.local-video-knowledge/bin/lvk` for a default install.
Substitute that executable for `lvk` in every command in this skill.

<!-- local-video-knowledge:wrapper -->

1. Resolve the input path the user gave. Quote it in every command: names often
   contain spaces. If the user describes the recordings instead of giving a path,
   find candidates with the agent's file search, show them, and ask which to use.
2. Resolve the vault in this order: the user's explicit argument, then
   `lvk config get vault --json`, then ask the user for the path and offer to save it
   with `lvk config set vault "/path/to/vault"`. Do not guess a personal vault path.
3. Confirm that the chosen directory exists and contains `.obsidian/`. Read the
   vault's own instructions (for example `CLAUDE.md`, `AGENTS.md` or a README at its
   root) before modifying notes. **The vault's rules win over this skill** on where
   new material goes, which status it starts with, its language and its naming. If
   the vault says new material enters an inbox or a sources folder as drafts, do that,
   and use `status: draft`.
4. Read `lvk config get --json`. `notes_language: auto` means the language spoken in
   the recording. Otherwise use the configured language for prose and section titles.
   Retain exact quotations in the spoken language and label translations when needed.
5. `no_dashes: true` is the default house style: normalize U+2013 and U+2014 in
   titles and exact quotations to a plain hyphen with surrounding spaces. This is the
   only permitted change to an exact quotation. Do not use those Unicode dashes
   elsewhere in notes, frontmatter, or your report. The user can disable this with
   `lvk config set no_dashes false`.
6. **Establish who is speaking** before you analyze. Ask the user if the file names,
   folder or vault do not make it clear. This decides how the notes are written:
   - **The vault owner speaking** (their own talks, posts, podcasts): the notes record
     the owner's own thinking. Attribute quotations to them by name, capture their
     principles, stories, frameworks and recurring phrases in their voice, and route
     them where the vault keeps the owner's own views. Never present them as advice
     from an outside expert, and never add claims they did not make.
   - **Someone else speaking**: treat it as an outside source, attributed to that
     speaker, as you would a book or a talk.
   - **A conversation** (interview, podcast with a host): the transcript does not
     label speakers. Attribute a passage to a named person only when the words
     themselves make it clear (for example a self-introduction, or a question
     followed by an answer addressed by name). Otherwise attribute it to "a speaker"
     and say that the attribution is uncertain. Never guess who said a passage.

Only if neither `lvk` nor the wrapper exists, tell the user to run this installer,
then resume after setup:

```bash
curl -fsSL https://raw.githubusercontent.com/ogabrielalonso/local-video-knowledge/main/install.sh | bash
```

## Principles

- Read the complete transcript of every file before writing any note.
- Prefer two or three excellent insights over ten shallow notes. No empty notes.
- Route by the dominant topic, not by the format. Before writing, search the vault
  with keywords and the agent's search tools, and use semantic search or an index
  note if the vault provides one. Find the existing topic cluster, write there, and
  connect the new notes bidirectionally with relevant siblings.
- Persist through long recordings and large folders. Track progress and continue
  until the end. If something blocks completion, report the actual blocker and keep
  the working files for recovery. Never claim partial analysis is complete.
- Clean up only this job's own working directory after successful validation.
  Never delete a glob such as `lvk_*` or another session's files.
- Never move, rename, edit or delete the user's recordings.

## Transcribe

```bash
lvk transcribe "PATH" --json
```

Use the real file or folder path. The command scans the media, then starts a
background worker and returns at once. Read the returned `workdir`, `lease`,
`files` and `total_duration`; use those exact values in later commands. Tell the
user how many files and how much audio were found, and that the first run
downloads the speech model (about 1.6 GB for the default `large-v3-turbo`).
If the same path was transcribed before, the state may already be `complete`:
finished files are reused unless the model, speech language or vocabulary changed
since, in which case they are transcribed again.

A folder is scanned recursively in natural name order. Supported: common video
formats (mp4, mov, m4v, mkv, webm, avi and others) and audio formats (mp3, m4a,
wav, aac, flac, ogg, opus and others). Hidden files and links are ignored. Only
the first audio track of each file is transcribed; if the user says a recording
keeps people on separate tracks, tell them only the first track is covered.

Then wait for the worker, in steps that fit your command timeout:

```bash
lvk status "WORKDIR" --wait 100 --json
```

`--wait` accepts up to 540 seconds; use the longest wait your command timeout
allows (in Claude Code, set the Bash timeout to 600000 ms and wait 540). Repeat
until `state` is `complete`. Report progress to the user between waits:
files finished, the current file and `eta_seconds` when present. On a recent
Apple Silicon Mac the default model usually transcribes several times faster than
real time; older or Intel machines are slower. If the user prefers speed over
accuracy, `lvk config set whisper_model small` before starting is faster and less
precise.

- `stopped` means the worker is no longer running (for example the computer slept
  or restarted). Run the same `lvk transcribe "PATH"` again: finished files are
  kept and the job resumes. That run returns a new lease; keep every lease you got.
- `failed` with a model error usually means no internet for the first model
  download, or not enough disk space. Report it plainly.
- Per-file `errors` do not stop the job. Report each failed file by name.
- `lvk stop "WORKDIR"` stops a running job when the user asks.

If names, brands or uncommon terms come out misspelled, offer to save them as
vocabulary, which guides spelling in future runs:
`lvk config set vocabulary "Name One, Brand Two, Term Three"`.
After saving it, run the same `lvk transcribe "PATH"` again: the files are
transcribed again with the new vocabulary. Otherwise fix obvious spelling of known
names in your notes, and say so.

When `state` is `complete`, the result lists `transcripts` (one file per recording,
with duration, recorded date and detected language) and `all_transcripts`, one
Markdown file with every transcript under a heading per recording, in order, with
skipped files marked.

Do not use raw ffmpeg, Whisper or improvised transcription scripts.

## Analyze everything before writing

1. Read the ENTIRE `all-transcripts.md` in blocks of approximately 650 lines.
   Continue from the last offset until the end, not just until enough material
   seems available. Track topics with their file and timestamp, exact quotations,
   stories, frameworks, recurring phrases, tools and actionable steps. A summary or
   a sample does not satisfy this step.
2. For a folder, look across the files: themes that recur in many recordings are
   usually the speaker's core ideas; note which files carry each theme.
3. Speech recognition makes mistakes, especially with names and mixed languages.
   When a passage is unclear, say it is unclear. Do not invent the missing words.
   Correct an obvious misspelling of a known name only, and never alter the meaning
   of a quotation. An exact quotation keeps the spoken words in their order. You may
   join words that the transcript splits across lines and mark omitted words with an
   ellipsis; never add, change or reorder words.
4. Synthesize BEFORE writing: the central message, three to five main concepts,
   what is distinctive versus generic, and practical takeaways. Separate what the
   speaker said from your interpretation. Name a speaker only when the user, the
   file or folder names, the vault or the recording itself establishes who it is.
   Otherwise write "the speaker" and state that the identity is unconfirmed.
5. Search the existing topic cluster now. Inspect likely siblings and any source
   INDEX. Decide the destination, what deserves a standalone insight, and which
   existing notes should receive reciprocal links.

## Keep the transcript as provenance

If the vault keeps raw sources (a sources or references folder, named in its
instructions or visible in its structure), save the transcript there as one note
per job, using the vault's conventions, so every claim can be traced back. Cite
files and timestamps in the knowledge notes, for example `(clip-07.mp4, 00:00:42)`.
If the vault has no such place, do not create one; the timestamps in the notes are
the provenance. The provenance transcript is a source file, not a knowledge note:
use the vault's conventions for sources, not the schema below, and do not pass it
to `lvk check`.

## Write substantial notes

One job (one file, or one folder) produces one MOC (overview) and usually two to
five insights, more for many hours of material when justified. A standalone
insight needs real substance: a concept explained at length or returned to across
several recordings, a framework, a step-by-step process, or equivalent standalone
value. Do not manufacture insights to reach a count. For a single short clip,
write the MOC only, unless the clip genuinely carries a standalone idea.

Use hyphen-separated filenames without special characters, at most 50 characters
including `.md`. Use descriptive ASCII slugs while keeping titles in the configured
notes language. Follow existing topic organization and naming conventions where
compatible. Link notes by file name without `.md`, for example
`[[note-file-name]]`, which Obsidian resolves anywhere in the vault. Existing notes
are the user's content. Never delete, rewrite, reorder,
or reformat existing text, and never change an existing note's title, filename, or
existing frontmatter values. Before writing to an existing note, record its current
content by reading it. After editing, confirm that the original text is still present
verbatim; if it is not, restore it before continuing.

Edits to existing notes are additive only. Append wikilinks to an existing Related
section, or add a Related section at the end if none exists. Add frontmatter keys
only when the vault already uses those keys. Optionally append one clearly headed
section at the end, such as `## From "<recording title>"`, with a short summary and
a link to the new MOC or insight. Never change existing frontmatter values or
content to fit this skill's schema.

When an existing note already covers a concept the recordings explain in depth,
write the new insight as a new note with a different, more specific filename and
link both ways. Mention this overlap in the report.

Each note has YAML frontmatter with these keys, in addition to any keys the vault
requires:

| Key | Value |
| --- | --- |
| `source` | `local-video` or `local-audio`, or an established source identifier required by the vault |
| `type` | `moc`, `insight`, `tactic`, or `principle` |
| `title` | Descriptive title |
| `description` | Dense, specific summary of the note's value |
| `source_title` | The file name without extension, or the folder name for a folder job |
| `source_path` | Absolute path of the file or folder that was transcribed |
| `duration` | Total duration in seconds, from `total_duration` |
| `recorded_date` | Recording date from the file metadata (earliest known date for a folder; say in the MOC how many files had one), or null if unknown |
| `tags` | A YAML list of meaningful topic tags |
| `status` | `active`, or the status the vault's rules ask for new material (for example `draft`) |
| `created`, `modified` | Actual dates in ISO format |
| `parent` | Quoted wikilink to the source INDEX for a MOC if one exists, otherwise null; insights link to the MOC |
| `related` | YAML list of quoted wikilinks to relevant existing sibling notes |

Use real values and quote wikilinks in YAML. Do not invent metadata or use filler.
In note bodies, write file paths and file names in backticks, so they stay exact.

### Size follows the material

`lvk check` sets minimum non-blank lines by `duration`, so a one-minute clip is
never padded into a lecture:

| Total duration | MOC | Each insight |
| --- | --- | --- |
| under 5 minutes | 30 | 25 |
| 5 to 15 minutes | 80 | 40 |
| 15 minutes or more | 150 | 50 |

These are floors for substance, not targets. If the material cannot support them,
say so instead of padding.

### MOC

Include all applicable sections, translated to the notes language:

- Metadata table: speaker, source path, number of recordings, total duration,
  recorded dates, transcription model.
- Central Message: one substantial paragraph.
- Overview: what the recordings cover and how they fit together.
- Key Concepts: dense explanation, exact quotation with file and timestamp, how to
  apply it, and a link to the corresponding insight when one exists.
- Recordings map (for a folder): a table of files, or groups of files, with their
  topic. For a long single recording: a table of timestamps and topics.
- Notable Quotations: exact, attributed statements with file and timestamp.
- Action Items: practical steps supported by the source.
- Related Notes: the relevant topic cluster and newly created insights.
- Processing footer: files transcribed, skipped files and why, total duration,
  model, and detected languages.

### Insights

An insight must be useful without reading the MOC. Include:

- Opening quotation with attribution.
- What It Is.
- The Problem It Solves.
- How It Works, with concrete steps.
- Practical Examples, from the recordings.
- Key Principles.
- When to Use and When NOT to Use.
- Related: MOC and relevant sibling notes.
- Source footer with the files and timestamps it draws on.

Remove a section that would otherwise be empty. Never leave placeholders, TODOs,
generic filler, or empty headings.

## Validate, connect, clean, report

1. Finish all new notes so their links can resolve. Run:

   ```bash
   lvk check "MOC_PATH" "INSIGHT_PATH" --vault "VAULT_PATH" --json
   ```

   Supply all new or updated source notes. Fix each failure: required frontmatter,
   minimum lines, forbidden dashes when enabled, and every wikilink. Validation
   checks structure and link targets, not the truth of your analysis. Review the
   content too. If the vault ships its own checks (for example a lint script named
   in its instructions), run them as well and fix what they report.
2. Add reciprocal links in the Related sections of the cited sibling notes and
   update the source INDEX if applicable, following the additive-only rules above.
3. After successful validation, release every lease this job returned, once each:
   `lvk clean "WORKDIR" --lease "LEASE" --json`. The directory is removed only after
   its last lease. If `remaining_leases` is still above zero after you released all
   of yours, another session or an earlier run holds the same job: that is normal.
   Report the retained workdir, and never try to release a lease you did not
   receive. Never use a shell deletion glob. On interruption, report the retained
   workdir and resume before cleanup.
4. Report: what was transcribed (files, total duration, skipped files and why,
   model, languages); each created note's path and real line count; validation
   outcome; reciprocal links and INDEX changes; and cleanup outcome. List every
   existing note touched and exactly what was appended. Mention overlap with
   existing notes and any unclear passages plainly. Report success only for
   actions actually completed.
