#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'EOF'
Usage: bash install.sh [--claude|--codex|--all] [--yes]
                      [--vault PATH] [--notes-language LANG] [--whisper-model MODEL]
Overrides: LVK_HOME, LVK_SOURCE, LVK_REF, CLAUDE_CONFIG_DIR, CODEX_HOME.
EOF
}

want_claude=0
want_codex=0
forced=0
assume_yes=0
vault=''
language=''
model=''
vault_given=0
language_given=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --claude) want_claude=1; forced=1; shift ;;
        --codex) want_codex=1; forced=1; shift ;;
        --all) want_claude=1; want_codex=1; forced=1; shift ;;
        --yes) assume_yes=1; shift ;;
        --vault|--notes-language|--whisper-model)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case "$1" in
                --vault) vault=$2; vault_given=1 ;;
                --notes-language) language=$2; language_given=1 ;;
                --whisper-model) model=$2 ;;
            esac
            shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

export LVK_HOME="${LVK_HOME:-$HOME/.local-video-knowledge}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
case "$LVK_HOME" in /*) ;; *) fail 'LVK_HOME must be an absolute path' ;; esac
[ "$LVK_HOME" != / ] && [ "$LVK_HOME" != "$HOME" ] || fail 'Unsafe LVK_HOME'
[ ! -L "$LVK_HOME" ] || fail 'LVK_HOME must not be a symbolic link'
bin_dir="$HOME/.local/bin"
home_created=1
if [ -e "$LVK_HOME" ]; then
    home_created=0
    [ -d "$LVK_HOME" ] || fail 'LVK_HOME must be a directory'
    LVK_HOME=$(cd "$LVK_HOME" && pwd -P)
    if [ -f "$LVK_HOME/.lvk-installation" ]; then
        grep -qx 'local-video-knowledge:managed' "$LVK_HOME/.lvk-installation" || fail 'Invalid installation marker'
        [ -f "$LVK_HOME/.lvk-manifest" ] || fail 'Marked installation has no ownership manifest'
    else
        # Unrelated files may survive uninstall. Never adopt an existing owned path.
        for reserved in src venv bin state config.json .lvk-installation .lvk-manifest .skill-targets; do
            if [ -e "$LVK_HOME/$reserved" ] || [ -L "$LVK_HOME/$reserved" ]; then
                fail "Refusing unmarked LVK_HOME with reserved path: $reserved"
            fi
        done
    fi
fi
mkdir -p "$LVK_HOME"
LVK_HOME=$(cd "$LVK_HOME" && pwd -P)
export LVK_HOME
[ "$LVK_HOME" != / ] && [ "$LVK_HOME" != "$(cd "$HOME" && pwd -P)" ] || fail 'Unsafe LVK_HOME'
mkdir -p "$bin_dir"
scratch=$(mktemp -d "${TMPDIR:-/tmp}/local-video-knowledge-install.XXXXXX")
trap 'rm -rf "$scratch"' EXIT

source_path="${LVK_SOURCE:-}"
if [ -z "$source_path" ] && [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
    if [ -f "$script_dir/pyproject.toml" ] && [ -f "$script_dir/SKILL.md" ]; then
        source_path=$script_dir
    fi
fi
mkdir -p "$scratch/src"
if [ -n "$source_path" ]; then
    [ -d "$source_path" ] || fail "LVK_SOURCE is not a directory: $source_path"
    source_path=$(cd "$source_path" && pwd -P)
    [ -f "$source_path/pyproject.toml" ] && [ -f "$source_path/SKILL.md" ] || fail 'Source is missing pyproject.toml or SKILL.md'
    # Copy only distributable source, excluding local caches and repositories.
    tar -C "$source_path" --exclude=__pycache__ -cf "$scratch/source.tar" pyproject.toml constraints.txt constraints.in README.md LICENSE SKILL.md CHANGELOG.md install.sh uninstall.sh local_video_knowledge
    tar -C "$scratch/src" -xf "$scratch/source.tar"
else
    [ "${LVK_OFFLINE_TEST:-0}" != 1 ] || fail 'LVK_OFFLINE_TEST requires LVK_SOURCE'
    curl -fsSL "https://api.github.com/repos/ogabrielalonso/local-video-knowledge/tarball/${LVK_REF:-main}" -o "$scratch/source.tar.gz"
    tar -xzf "$scratch/source.tar.gz" -C "$scratch/src" --strip-components=1
fi
[ -f "$scratch/src/pyproject.toml" ] && [ -f "$scratch/src/SKILL.md" ] && [ -f "$scratch/src/constraints.txt" ] || fail 'Downloaded source is incomplete'
if [ ! -f "$LVK_HOME/.lvk-installation" ]; then
    printf '%s\n' 'local-video-knowledge:managed' > "$LVK_HOME/.lvk-installation"
    printf '%s\n' 'home:src' 'home:venv' 'home:bin' 'home:.lvk-installation' \
        'home:.lvk-manifest' 'home:.skill-targets' > "$LVK_HOME/.lvk-manifest"
    if [ "$home_created" = 1 ]; then
        printf '%s\n' 'home-dir:created' >> "$LVK_HOME/.lvk-manifest"
    fi
fi
# Runtime state is recursively owned; unrecorded existing paths are never adopted.
if ! grep -qx 'home:state' "$LVK_HOME/.lvk-manifest"; then
    [ ! -e "$LVK_HOME/state" ] && [ ! -L "$LVK_HOME/state" ] || fail 'Refusing unrecorded state directory'
    printf '%s\n' 'home:state' >> "$LVK_HOME/.lvk-manifest"
fi
[ ! -L "$LVK_HOME/state" ] || fail 'state must not be a symbolic link'
mkdir -p "$LVK_HOME/state"
# Record configuration before runtime commands can create it.
if [ ! -e "$LVK_HOME/config.json" ]; then
    printf '{}\n' > "$LVK_HOME/config.json"
    printf '%s\n' 'home:config.json' >> "$LVK_HOME/.lvk-manifest"
fi
if [ -e "$LVK_HOME/src" ]; then
    [ ! -L "$LVK_HOME/src" ] || fail 'src must not be a symbolic link'
    rm -rf "$LVK_HOME/src"
fi
mv "$scratch/src" "$LVK_HOME/src"

if [ "${LVK_OFFLINE_TEST:-0}" = 1 ]; then
    printf '%s\n' 'OFFLINE TEST: Python environment and dependency installation are stubbed.'
    mkdir -p "$LVK_HOME/venv/bin"
    test_python="${LVK_TEST_PYTHON:-$(command -v python3)}"
    ln -sf "$test_python" "$LVK_HOME/venv/bin/python"
    cat > "$LVK_HOME/venv/bin/lvk" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$LVK_HOME/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$LVK_HOME/venv/bin/python" -m local_video_knowledge.cli "$@"
EOF
    chmod +x "$LVK_HOME/venv/bin/lvk"
else
    if command -v uv >/dev/null 2>&1; then
        uv_bin=$(command -v uv)
    elif [ -x "$bin_dir/uv" ]; then
        uv_bin="$bin_dir/uv"
    else
        curl -fsSL https://astral.sh/uv/install.sh -o "$scratch/uv-install.sh"
        UV_INSTALL_DIR="$bin_dir" UV_NO_MODIFY_PATH=1 sh "$scratch/uv-install.sh"
        uv_bin="$bin_dir/uv"
    fi
    [ ! -L "$LVK_HOME/bin" ] && [ ! -L "$LVK_HOME/venv" ] || fail 'bin and venv must not be symbolic links'
    if [ ! -x "$LVK_HOME/venv/bin/python" ]; then
        "$uv_bin" venv --python 3.12 "$LVK_HOME/venv"
    fi
    "$uv_bin" pip install --upgrade --python "$LVK_HOME/venv/bin/python" \
        -c "$LVK_HOME/src/constraints.txt" --build-constraints "$LVK_HOME/src/constraints.txt" \
        "$LVK_HOME/src"
fi

# A wrapper retains custom LVK_HOME even in a later shell without the override.
[ ! -L "$LVK_HOME/bin" ] && [ ! -L "$LVK_HOME/venv" ] || fail 'bin and venv must not be symbolic links'
mkdir -p "$LVK_HOME/bin"
# Write a new file and rename it, so an existing link is replaced, never followed.
{
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'export LVK_HOME=%q\n' "$LVK_HOME"
    printf 'exec "$LVK_HOME/venv/bin/lvk" "$@"\n'
} > "$LVK_HOME/bin/.lvk-wrapper.$$"
chmod +x "$LVK_HOME/bin/.lvk-wrapper.$$"
mv -f "$LVK_HOME/bin/.lvk-wrapper.$$" "$LVK_HOME/bin/lvk"
if [ -e "$bin_dir/lvk" ] || [ -L "$bin_dir/lvk" ]; then
    if [ ! -L "$bin_dir/lvk" ] || [ "$(readlink "$bin_dir/lvk")" != "$LVK_HOME/bin/lvk" ]; then
        backup="$bin_dir/lvk.bak-$(date +%Y%m%d%H%M%S)-$$"
        mv "$bin_dir/lvk" "$backup"
        printf 'Backed up existing lvk: %s\n' "$backup"
    fi
fi
ln -sf "$LVK_HOME/bin/lvk" "$bin_dir/lvk"
printf 'link:%s\n' "$bin_dir/lvk" >> "$LVK_HOME/.lvk-manifest"

if [ "$forced" = 0 ]; then
    if [ -d "$CLAUDE_CONFIG_DIR" ] || command -v claude >/dev/null 2>&1; then want_claude=1; fi
    if [ -d "$CODEX_HOME" ] || command -v codex >/dev/null 2>&1; then want_codex=1; fi
    if [ "$want_claude" = 0 ] && [ "$want_codex" = 0 ]; then
        want_claude=1
        want_codex=1
        printf '%s\n' 'Neither agent detected; installing the skill for both Claude Code and Codex.'
    fi
fi
# Render once so reinstall comparisons use the installed, customized content.
"$LVK_HOME/venv/bin/python" - "$LVK_HOME/src/SKILL.md" "$scratch/SKILL.md" "$LVK_HOME/bin/lvk" "$LVK_HOME" <<'PY'
from pathlib import Path
import shlex
import sys

source, destination, wrapper, installation_id = sys.argv[1:]
text = Path(source).read_text(encoding="utf-8")
marker = "<!-- local-video-knowledge:wrapper -->"
if text.splitlines().count(marker) != 1:
    raise SystemExit("SKILL.md must contain exactly one wrapper placeholder line")
# Double quotes are readable for ordinary paths; shlex handles shell metacharacters.
command = '"' + wrapper + '"' if not any(c in wrapper for c in '\\"$`\n') else shlex.quote(wrapper)
text = text.replace("<!-- local-video-knowledge:managed -->",
                    f"<!-- local-video-knowledge:managed installation-id:{installation_id} -->")
Path(destination).write_text(text.replace(marker, f"Installed wrapper: `{command}`"), encoding="utf-8")
PY
install_skill() {
    target="$1/skills/local-video-knowledge"
    mkdir -p "$target"
    target=$(cd "$target" && pwd -P)
    if [ -e "$target/SKILL.md" ] || [ -L "$target/SKILL.md" ]; then
        if ! cmp -s "$scratch/SKILL.md" "$target/SKILL.md"; then
            backup="$target/SKILL.md.bak-$(date +%Y%m%d%H%M%S)-$$"
            mv "$target/SKILL.md" "$backup"
            printf 'Backed up existing skill: %s\n' "$backup"
        elif [ -L "$target/SKILL.md" ]; then
            rm "$target/SKILL.md"
        fi
    fi
    cp "$scratch/SKILL.md" "$target/SKILL.md"
    printf '%s\n' "$target" >> "$LVK_HOME/.skill-targets"
    printf 'skill:%s\n' "$target" >> "$LVK_HOME/.lvk-manifest"
    printf 'Installed skill: %s\n' "$target/SKILL.md"
}
if [ "$want_claude" = 1 ]; then install_skill "$CLAUDE_CONFIG_DIR"; fi
if [ "$want_codex" = 1 ]; then install_skill "$CODEX_HOME"; fi
awk '!seen[$0]++' "$LVK_HOME/.skill-targets" > "$scratch/skill-targets"
mv "$scratch/skill-targets" "$LVK_HOME/.skill-targets"
awk '!seen[$0]++' "$LVK_HOME/.lvk-manifest" > "$scratch/lvk-manifest"
mv "$scratch/lvk-manifest" "$LVK_HOME/.lvk-manifest"

if [ "$assume_yes" = 0 ] && ( : </dev/tty ) 2>/dev/null; then
    if [ "$vault_given" = 0 ]; then
        printf 'Obsidian vault path (Enter to keep current setting): ' >/dev/tty
        IFS= read -r vault </dev/tty || true
    fi
    if [ "$language_given" = 0 ]; then
        printf 'Notes language (auto = language spoken in the recording, Enter to keep current setting): ' >/dev/tty
        IFS= read -r language </dev/tty || true
    fi
fi
if [ -n "$vault" ]; then "$LVK_HOME/bin/lvk" config set vault "$vault"; fi
if [ -n "$language" ]; then "$LVK_HOME/bin/lvk" config set notes_language "$language"; fi
if [ -z "$vault" ]; then
    printf '%s\n' 'If the vault is unset, configure it with: lvk config set vault /path/to/vault'
fi
if [ -n "$model" ]; then
    "$LVK_HOME/bin/lvk" config set whisper_model "$model"
    if [ "${LVK_OFFLINE_TEST:-0}" != 1 ]; then
        "$LVK_HOME/venv/bin/python" -c 'from faster_whisper import WhisperModel; import sys; WhisperModel(sys.argv[1], device="cpu", compute_type="int8")' "$model"
    fi
else
    printf '%s\n' 'The Whisper model (large-v3-turbo by default, about 1.6 GB) downloads on the first transcription.'
fi
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *)
        path_line='export PATH="$HOME/.local/bin:$PATH"'
        printf '%s\n' '~/.local/bin is not on PATH. Add this line to your shell configuration:' "$path_line"
        rc_file=''
        user_shell="${SHELL:-}"
        case "${user_shell##*/}" in
            zsh) rc_file="$HOME/.zshrc" ;;
            bash)
                rc_file="$HOME/.bashrc"
                if [ "$(uname -s)" = Darwin ]; then
                    if [ -f "$HOME/.bash_profile" ] || [ ! -f "$rc_file" ]; then
                        rc_file="$HOME/.bash_profile"
                    fi
                fi ;;
        esac
        if [ "$assume_yes" = 0 ] && [ -n "$rc_file" ] && ( : </dev/tty ) 2>/dev/null; then
            if [ -f "$rc_file" ] && grep -Fqx "$path_line" "$rc_file"; then
                printf 'PATH line already present in %s. Open a new shell to use it.\n' "$rc_file"
            else
                printf 'Append this PATH line to %s? [y/N] ' "$rc_file" >/dev/tty
                answer=''
                IFS= read -r answer </dev/tty || true
                case "$answer" in
                    y|Y|yes|YES)
                        printf '\n%s\n' "$path_line" >> "$rc_file"
                        printf 'Updated %s. Open a new shell to use it.\n' "$rc_file" ;;
                esac
            fi
        fi ;;
esac
if [ "${LVK_OFFLINE_TEST:-0}" = 1 ]; then
    printf '%s\n' 'OFFLINE TEST: doctor skipped; dependencies were not installed.'
elif ! "$LVK_HOME/bin/lvk" doctor; then
    printf '%s\n' 'Installation finished, but doctor found issues. Resolve the FAIL lines, then run lvk doctor again.'
fi
printf 'CLI available now: "%s"\n' "$LVK_HOME/bin/lvk"
printf '%s\n' 'Next: Claude Code: /local-video-knowledge <file or folder>' '      Codex: $local-video-knowledge <file or folder> (or ask in natural language)'
