#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
waybar_dir="$config_home/waybar"
hypr_scripts_dir="$config_home/hypr/scripts"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$config_home/debian-hyprland-custom-backup-$timestamp"

for command_name in waybar playerctl cava jq python3; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Dépendance manquante : %s\n' "$command_name" >&2
        exit 1
    fi
done

mkdir -p "$backup_dir/waybar" "$waybar_dir/configs" "$waybar_dir/styles" "$hypr_scripts_dir"

for path in \
    "$waybar_dir/config" \
    "$waybar_dir/style.css" \
    "$waybar_dir/configs/[CUSTOM] Debian Glass" \
    "$waybar_dir/styles/[CUSTOM] Debian Glass.css"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a "$path" "$backup_dir/waybar/"
    fi
done

cp -a "$repo_dir/config/waybar/." "$waybar_dir/"
cp -a "$repo_dir/config/hypr/scripts/." "$hypr_scripts_dir/"
chmod +x \
    "$waybar_dir/media-panel-toggle.sh" \
    "$waybar_dir/media-panel.py" \
    "$waybar_dir/debian-glass-stats.sh" \
    "$waybar_dir/power-profile-menu.sh" \
    "$waybar_dir/workspace-label.sh" \
    "$hypr_scripts_dir/WaybarCava.sh"

ln -sfn "$waybar_dir/configs/[CUSTOM] Debian Glass" "$waybar_dir/config"
ln -sfn "$waybar_dir/styles/[CUSTOM] Debian Glass.css" "$waybar_dir/style.css"

pkill -SIGUSR2 -x waybar 2>/dev/null || true

printf 'Debian Glass installé. Sauvegarde : %s\n' "$backup_dir"
