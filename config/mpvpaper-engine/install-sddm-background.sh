#!/usr/bin/env bash

set -euo pipefail

image="${1:-}"
theme_dir="/usr/share/sddm/themes/simple_sddm_2"
theme_file="$theme_dir/Main.qml"
target="$theme_dir/login-background.jpeg"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
patch_file="$script_dir/sddm-background.patch"

if [ "$(id -u)" -ne 0 ]; then
    printf 'Cette commande doit être exécutée avec sudo ou pkexec.\n' >&2
    exit 1
fi
if [ ! -f "$image" ]; then
    printf 'Image extraite introuvable : %s\n' "$image" >&2
    exit 1
fi
if [ ! -f "$theme_file" ]; then
    printf 'Thème SDDM simple_sddm_2 introuvable.\n' >&2
    exit 1
fi

backup="$theme_file.before-mpvpaper-engine"
[ -f "$backup" ] || cp -a "$theme_file" "$backup"

if ! rg -q '^[[:space:]]*source: "login-background.jpeg"' "$theme_file"; then
    patch --forward -p1 -d / <"$patch_file"
fi

install -m 0644 "$image" "$target"
printf 'Fond de connexion installé : %s\n' "$target"
