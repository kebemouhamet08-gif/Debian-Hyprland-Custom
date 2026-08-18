#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
caelestia_dir="$config_home/caelestia"
hypr_dir="$config_home/hypr"
hypr_main="$hypr_dir/hyprland.conf"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$config_home/debian-immersive-v2-backup-$timestamp"
source_line="source = $hypr_dir/caelestia-v2.conf"

if ! command -v Hyprland >/dev/null 2>&1 && ! command -v hyprctl >/dev/null 2>&1; then
    printf 'Hyprland est requis avant Debian Immersive v2.\n' >&2
    exit 1
fi

missing=()
command -v qs >/dev/null 2>&1 || missing+=("Quickshell git (qs)")
if [ ! -x "$HOME/.nix-profile/bin/caelestia" ] && ! command -v caelestia >/dev/null 2>&1; then
    missing+=("caelestia-cli")
fi
if ((${#missing[@]})); then
    printf 'Prérequis Caelestia manquants : %s\n' "$(IFS=', '; printf '%s' "${missing[*]}")" >&2
    printf 'Installez-les selon la documentation officielle, puis relancez ce script.\n' >&2
    exit 1
fi

mkdir -p "$backup_dir" "$caelestia_dir" "$hypr_dir/scripts"

for path in "$caelestia_dir/shell.json" "$hypr_dir/caelestia-v2.conf" \
    "$hypr_dir/scripts/caelestia-v2-launch.sh" \
    "$hypr_dir/scripts/caelestia-v2-lock.sh" \
    "$hypr_dir/scripts/caelestia-v2-display-profile.sh" "$hypr_main"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a --parents "$path" "$backup_dir/"
    fi
done

install -m 0644 "$repo_dir/config/caelestia/shell.json" "$caelestia_dir/shell.json"
install -m 0644 "$repo_dir/config/hypr/caelestia-v2.conf" "$hypr_dir/caelestia-v2.conf"
install -m 0755 "$repo_dir/config/hypr/scripts/caelestia-v2-launch.sh" \
    "$hypr_dir/scripts/caelestia-v2-launch.sh"
install -m 0755 "$repo_dir/config/hypr/scripts/caelestia-v2-lock.sh" \
    "$hypr_dir/scripts/caelestia-v2-lock.sh"
install -m 0755 "$repo_dir/config/hypr/scripts/caelestia-v2-display-profile.sh" \
    "$hypr_dir/scripts/caelestia-v2-display-profile.sh"

if [ ! -f "$hypr_main" ]; then
    printf '%s\n' "$source_line" >"$hypr_main"
elif ! grep -Fqx "$source_line" "$hypr_main"; then
    printf '\n# Debian Immersive v2\n%s\n' "$source_line" >>"$hypr_main"
fi

mkdir -p "$HOME/Pictures/Wallpapers"
hyprctl reload >/dev/null 2>&1 || true

printf 'Debian Immersive v2 installé. Sauvegarde : %s\n' "$backup_dir"
printf 'Relancez la session, ou exécutez : %s\n' "$hypr_dir/scripts/caelestia-v2-launch.sh"
