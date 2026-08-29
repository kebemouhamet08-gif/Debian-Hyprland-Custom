#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
waybar_dir="$config_home/waybar"
hypr_scripts_dir="$config_home/hypr/scripts"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$config_home/debian-hyprland-custom-backup-$timestamp"

check_dependencies() {
    local variant="${1:-nova}" command_name failed=0
    for command_name in waybar playerctl cava jq python3; do
        if command -v "$command_name" >/dev/null 2>&1; then
            printf 'OK       %s\n' "$command_name"
        else
            printf 'MANQUANT %s\n' "$command_name" >&2
            failed=1
        fi
    done
    if python3 -c "import gi; gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')" \
        2>/dev/null; then
        printf 'OK       GTK3 pour Python\n'
    else
        printf 'MANQUANT python3-gi ou gir1.2-gtk-3.0\n' >&2
        failed=1
    fi
    if [ "$variant" = nova ]; then
        for command_name in brightnessctl cliphist grim hyprpicker powerprofilesctl slurp swaync-client wl-copy; do
            if command -v "$command_name" >/dev/null 2>&1; then
                printf 'OK       %s (Nova Lite)\n' "$command_name"
            else
                printf 'OPTIONNEL %s (fonction Nova Lite associée indisponible)\n' "$command_name"
            fi
        done
    fi
    return "$failed"
}

action="${1:-install}"
variant="${2:-nova}"
case "$variant" in
    bar)
        config_name='[Deblestia] Bar'
        style_name='[Deblestia] Bar.css'
        product_name='Deblestia Bar'
        ;;
    nova)
        config_name='[Deblestia] Nova Lite'
        style_name='[Deblestia] Nova Lite.css'
        product_name='Deblestia Nova Lite'
        ;;
    *)
        printf 'Variante inconnue : %s (bar ou nova attendu)\n' "$variant" >&2
        exit 2
        ;;
esac
if [ "$action" = check ]; then
    check_dependencies "$variant"
    exit
fi
if [ "$action" != install ]; then
    printf 'Usage : %s [check|install] [bar|nova]\n' "$0" >&2
    exit 2
fi

check_dependencies "$variant"

mkdir -p "$backup_dir/waybar" "$waybar_dir/configs" "$waybar_dir/styles" "$hypr_scripts_dir"

for path in \
    "$waybar_dir/config" \
    "$waybar_dir/style.css" \
    "$waybar_dir/panel-colors.css" \
    "$waybar_dir/theme-overrides.css" \
    "$waybar_dir/configs/[CUSTOM] Debian Glass" \
    "$waybar_dir/styles/[CUSTOM] Debian Glass.css" \
    "$waybar_dir/configs/[Deblestia] Bar" \
    "$waybar_dir/styles/[Deblestia] Bar.css" \
    "$waybar_dir/configs/[Deblestia] Nova Lite" \
    "$waybar_dir/styles/[Deblestia] Nova Lite.css"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a "$path" "$backup_dir/waybar/"
    fi
done

cp -a "$repo_dir/config/waybar/." "$waybar_dir/"
cp -a "$repo_dir/config/hypr/scripts/." "$hypr_scripts_dir/"
ln -sfn ../panel-colors.css "$waybar_dir/styles/panel-colors.css"
if [ "$variant" = nova ]; then
    rm -f "$waybar_dir/configs/[Deblestia] Bar" \
        "$waybar_dir/styles/[Deblestia] Bar.css"
fi
for color_file in panel-colors.css theme-overrides.css; do
    if [ -f "$backup_dir/waybar/$color_file" ]; then
        cp -a "$backup_dir/waybar/$color_file" "$waybar_dir/$color_file"
    fi
done
chmod +x \
    "$waybar_dir/media-panel-toggle.sh" \
    "$waybar_dir/media-panel.py" \
    "$waybar_dir/deblestia-bar-stats.sh" \
    "$waybar_dir/deblestia-updates.sh" \
    "$waybar_dir/deblestia-theme.sh" \
    "$waybar_dir/deblestia-focus.py" \
    "$waybar_dir/deblestia-notes.sh" \
    "$waybar_dir/deblestia-waybar-switch.sh" \
    "$waybar_dir/power-profile-menu.sh" \
    "$waybar_dir/workspace-label.sh" \
    "$hypr_scripts_dir/WaybarCava.sh"

ln -sfn "$waybar_dir/configs/$config_name" "$waybar_dir/config"
ln -sfn "$waybar_dir/styles/$style_name" "$waybar_dir/style.css"

if [ -x "$hypr_scripts_dir/desktop-shell-mode.sh" ]; then
    "$hypr_scripts_dir/desktop-shell-mode.sh" "$config_name"
else
    pkill -SIGUSR2 -x waybar 2>/dev/null || true
fi

printf '%s installé. Sauvegarde : %s\n' "$product_name" "$backup_dir"
