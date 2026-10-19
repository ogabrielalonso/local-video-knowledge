#!/usr/bin/env bash
set -euo pipefail

LVK_HOME="${LVK_HOME:-$HOME/.local-video-knowledge}"
case "$LVK_HOME" in /*) ;; *) printf '%s\n' 'Error: LVK_HOME must be absolute' >&2; exit 1 ;; esac
if [ ! -d "$LVK_HOME" ]; then
    printf '%s\n' 'local-video-knowledge is already absent.'
    exit 0
fi
if [ -L "$LVK_HOME" ]; then
    printf '%s\n' 'Error: refusing a symlinked LVK_HOME' >&2
    exit 1
fi
LVK_HOME=$(cd "$LVK_HOME" && pwd -P)
if [ "$LVK_HOME" = / ] || [ "$LVK_HOME" = "$(cd "$HOME" && pwd -P)" ] || ! grep -qx 'local-video-knowledge:managed' "$LVK_HOME/.lvk-installation" || [ ! -f "$LVK_HOME/.lvk-manifest" ]; then
    printf '%s\n' 'Error: refusing to remove an unmarked or unsafe installation directory' >&2
    exit 1
fi
# Removing state while a worker runs would drop the locks that protect its work.
# Read the process list first, so the check never matches its own command line.
processes=$(ps -axo command= 2>/dev/null || true)
if [[ "$processes" == *"$LVK_HOME/venv/bin/python -m local_video_knowledge.job"* ]]; then
    printf '%s\n' 'Error: a transcription is still running. Wait for it, or stop it with lvk stop WORKDIR, then uninstall.' >&2
    exit 1
fi
remove_skill() {
    target="$1/SKILL.md"
    if [ -f "$target" ] && grep -qFx "<!-- local-video-knowledge:managed installation-id:$LVK_HOME -->" "$target"; then
        rm "$target"
        rmdir "$1" 2>/dev/null || true
        printf 'Removed managed skill: %s\n' "$target"
    fi
}
home_created=0
while IFS= read -r owned; do
    case "$owned" in
        home-dir:created) home_created=1 ;;
        skill:*/skills/local-video-knowledge) remove_skill "${owned#skill:}" ;;
        link:*/lvk)
            link=${owned#link:}
            if [ -L "$link" ] && [ "$(readlink "$link")" = "$LVK_HOME/bin/lvk" ]; then rm "$link"; fi ;;
        home:src|home:venv|home:bin|home:state)
            path="$LVK_HOME/${owned#home:}"
            [ ! -L "$path" ] || { printf 'Error: refusing symlinked owned path: %s\n' "$path" >&2; exit 1; }
            rm -rf "$path" ;;
        home:config.json|home:.skill-targets|home:.lvk-installation)
            rm -f "$LVK_HOME/${owned#home:}" ;;
        home:.lvk-manifest) ;;
        *) printf 'Error: invalid manifest entry: %s\n' "$owned" >&2; exit 1 ;;
    esac
done < "$LVK_HOME/.lvk-manifest"
rm "$LVK_HOME/.lvk-manifest"
if [ "$home_created" = 1 ]; then rmdir "$LVK_HOME" 2>/dev/null || true; fi
printf '%s\n' 'Removed local-video-knowledge. Vault notes, temporary video workdirs, skill backups, uv and shared model caches were preserved.'
