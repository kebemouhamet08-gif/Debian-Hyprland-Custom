#!/usr/bin/env bash

set -euo pipefail

notes_dir="${XDG_DATA_HOME:-$HOME/.local/share}/deblestia"
notes_file="$notes_dir/notes.md"
mkdir -p "$notes_dir"
if [ ! -f "$notes_file" ]; then
    printf '# Notes Deblestia\n\n- [ ] Première tâche\n' >"$notes_file"
fi

for editor in nvim vim nano; do
    if command -v "$editor" >/dev/null 2>&1 && command -v kitty >/dev/null 2>&1; then
        exec kitty --class deblestia-notes -e "$editor" "$notes_file"
    fi
done

for editor in gnome-text-editor mousepad kate; do
    if command -v "$editor" >/dev/null 2>&1; then
        exec "$editor" "$notes_file"
    fi
done

exec xdg-open "$notes_file"
