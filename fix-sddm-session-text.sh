#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
theme_file="/usr/share/sddm/themes/simple_sddm_2/Main.qml"
patch_file="$repo_dir/fixes/sddm-session-text.patch"
background_patch="$repo_dir/fixes/sddm-background.patch"
backup_file="$theme_file.before-session-text-fix"
wallpaper="${1:-$HOME/Pictures/wallpapers/Gemini_Generated_Image_o54hveo54hveo54h.jpeg}"
theme_wallpaper="$(dirname "$theme_file")/login-background.jpeg"

if [[ ! -f "$theme_file" ]]; then
    printf 'Thème SDDM introuvable : %s\n' "$theme_file" >&2
    exit 1
fi

if [[ ! -f "$wallpaper" ]]; then
    printf 'Fond d’écran introuvable : %s\n' "$wallpaper" >&2
    printf 'Utilisation : %s /chemin/vers/image.jpeg\n' "$0" >&2
    exit 1
fi

if [[ ! -f "$backup_file" ]]; then
    sudo cp -a "$theme_file" "$backup_file"
fi

if ! rg -q '^[[:space:]]*textRole:' "$theme_file"; then
    patch --dry-run --forward -p1 -d / < "$patch_file" >/dev/null
    printf 'Correction du texte des sessions…\n'
    sudo patch --forward -p1 -d / < "$patch_file"
fi

if ! rg -q 'source: "login-background.jpeg"' "$theme_file"; then
    patch --dry-run --forward -p1 -d / < "$background_patch" >/dev/null
    printf 'Correction du chemin du fond d’écran…\n'
    sudo patch --forward -p1 -d / < "$background_patch"
fi

printf 'Copie du fond d’écran dans le thème SDDM…\n'
sudo install -m 0644 "$wallpaper" "$theme_wallpaper"

printf 'Corrections installées. Redémarrez la machine pour les voir.\n'
printf 'Sauvegarde : %s\n' "$backup_file"
