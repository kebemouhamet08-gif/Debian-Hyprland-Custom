#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
waybar_dir="$config_home/waybar"
hypr_dir="$config_home/hypr"
hypr_scripts_dir="$config_home/hypr/scripts"
hypr_user_scripts_dir="$config_home/hypr/UserScripts"
hypr_main="$hypr_dir/hyprland.conf"
input_include="$hypr_dir/deblestia-input.conf"
input_source="source = $input_include"
workspace_include="$hypr_dir/deblestia-workspaces.conf"
workspace_source="source = $workspace_include"
ui_include="$hypr_dir/deblestia-ui.conf"
ui_source="source = $ui_include"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$config_home/debian-hyprland-custom-backup-$timestamp"
ui_state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia"
ui_state_file="$ui_state_dir/ui-mode"

check_dependencies() {
    local command_name failed=0
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
    for command_name in brightnessctl cliphist grim hyprpicker powerprofilesctl slurp swaync-client wl-copy; do
        if command -v "$command_name" >/dev/null 2>&1; then
            printf 'OK       %s (Nova 2)\n' "$command_name"
        else
            printf 'OPTIONNEL %s (fonction Nova 2 associée indisponible)\n' "$command_name"
        fi
    done
    return "$failed"
}

action="${1:-install}"
variant="${2:-nova2}"
case "$variant" in
    nova2)
        variant='nova2'
        mode='nova2'
        config_name='[Deblestia] Nova 2'
        style_name='[Deblestia] Nova 2.css'
        product_name='Deblestia Nova 2'
        ;;
    *)
        printf 'Variante supprimée : %s (seul nova2 est disponible)\n' "$variant" >&2
        exit 2
        ;;
esac
if [ "$action" = check ]; then
    check_dependencies
    exit
fi
if [ "$action" != install ]; then
    printf 'Usage : %s [check|install] [nova2]\n' "$0" >&2
    exit 2
fi

check_dependencies

mkdir -p "$backup_dir/waybar" "$backup_dir/hypr" "$waybar_dir/configs" \
    "$waybar_dir/styles" "$hypr_scripts_dir"
mkdir -p "$hypr_user_scripts_dir"

for path in \
    "$waybar_dir/config" \
    "$waybar_dir/style.css" \
    "$waybar_dir/panel-colors.css" \
    "$waybar_dir/theme-overrides.css" \
    "$waybar_dir/configs/[CUSTOM] Debian Glass" \
    "$waybar_dir/styles/[CUSTOM] Debian Glass.css" \
    "$waybar_dir/configs/[Deblestia] Bar" \
    "$waybar_dir/styles/[Deblestia] Bar.css" \
    "$waybar_dir/configs/[Deblestia] Nova 2" \
    "$waybar_dir/styles/[Deblestia] Nova 2.css" \
    "$waybar_dir/configs/[Deblestia] Nova Lite" \
    "$waybar_dir/styles/[Deblestia] Nova Lite.css"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a "$path" "$backup_dir/waybar/"
    fi
done

for path in "$hypr_main" "$input_include" "$workspace_include" "$ui_include"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a "$path" "$backup_dir/hypr/"
    fi
done

cp -a "$repo_dir/config/waybar/." "$waybar_dir/"
rm -f \
    "$waybar_dir/configs/[CUSTOM] Debian Glass" \
    "$waybar_dir/styles/[CUSTOM] Debian Glass.css" \
    "$waybar_dir/configs/[Deblestia] Bar" \
    "$waybar_dir/styles/[Deblestia] Bar.css" \
    "$waybar_dir/configs/[Deblestia] Nova" \
    "$waybar_dir/configs/[Deblestia] Nova Lite" \
    "$waybar_dir/styles/[Deblestia] Nova Lite.css" \
    "$waybar_dir/debian-glass-spotify.css" \
    "$waybar_dir/deblestia-bar-stats.sh" \
    "$waybar_dir/workspace-label.sh"
cp -a "$repo_dir/config/hypr/scripts/." "$hypr_scripts_dir/"
install -m 0755 "$repo_dir/config/hypr/UserScripts/WaybarWallpaperSync.sh" \
    "$hypr_user_scripts_dir/WaybarWallpaperSync.sh"
install -m 0755 "$repo_dir/config/hypr/UserScripts/MinimizeWindow.sh" \
    "$hypr_user_scripts_dir/MinimizeWindow.sh"
install -m 0755 "$repo_dir/config/hypr/UserScripts/RestoreMinimizedWindow.sh" \
    "$hypr_user_scripts_dir/RestoreMinimizedWindow.sh"
install -m 0644 "$repo_dir/config/hypr/deblestia-input.conf" "$input_include"
install -m 0644 "$repo_dir/config/hypr/deblestia-workspaces.conf" "$workspace_include"
install -m 0644 "$repo_dir/config/hypr/deblestia-ui.conf" "$ui_include"
if [ ! -f "$hypr_main" ]; then
    printf '%s\n%s\n%s\n' "$ui_source" "$workspace_source" "$input_source" >"$hypr_main"
else
    if ! grep -Fqx "$ui_source" "$hypr_main"; then
        printf '\n# Gestionnaire des interfaces Deblestia\n%s\n' "$ui_source" >>"$hypr_main"
    fi
    if ! grep -Fqx "$workspace_source" "$hypr_main"; then
        printf '\n# Workspaces multi-écran Deblestia\n%s\n' "$workspace_source" >>"$hypr_main"
    fi
    if ! grep -Fqx "$input_source" "$hypr_main"; then
        printf '\n# Navigation souris et pavé tactile Deblestia\n%s\n' "$input_source" >>"$hypr_main"
    fi
fi
ln -sfn ../panel-colors.css "$waybar_dir/styles/panel-colors.css"
for color_file in panel-colors.css theme-overrides.css; do
    if [ -f "$backup_dir/waybar/$color_file" ]; then
        cp -a "$backup_dir/waybar/$color_file" "$waybar_dir/$color_file"
    fi
done
chmod +x \
    "$waybar_dir/media-panel-toggle.sh" \
    "$waybar_dir/media-panel.py" \
    "$waybar_dir/deblestia-system-stats.sh" \
    "$waybar_dir/deblestia-updates.sh" \
    "$waybar_dir/deblestia-theme.sh" \
    "$waybar_dir/deblestia-focus.py" \
    "$waybar_dir/deblestia-notes.sh" \
    "$waybar_dir/deblestia-waybar-switch.sh" \
    "$waybar_dir/power-profile-menu.sh" \
    "$hypr_scripts_dir/WaybarCava.sh" \
    "$hypr_scripts_dir/desktop-shell-mode.sh" \
    "$hypr_scripts_dir/deblestia-nova-shell-launch.sh" \
    "$hypr_scripts_dir/deblestia-workspace-action.sh" \
    "$hypr_scripts_dir/OverviewToggle.sh" \
    "$hypr_scripts_dir/Wlogout.sh" \
    "$hypr_scripts_dir/WaybarLayout.sh"

ln -sfn "$waybar_dir/configs/$config_name" "$waybar_dir/config"
ln -sfn "$waybar_dir/styles/$style_name" "$waybar_dir/style.css"
mkdir -p "$ui_state_dir"
printf '%s\n' "$mode" >"$ui_state_file"

if [ -x "$hypr_scripts_dir/desktop-shell-mode.sh" ]; then
    "$hypr_scripts_dir/desktop-shell-mode.sh" "$mode"
else
    pkill -SIGUSR2 -x waybar 2>/dev/null || true
fi
if command -v hyprctl >/dev/null 2>&1; then
    hyprctl reload >/dev/null 2>&1 || true
fi

printf '%s installé. Sauvegarde : %s\n' "$product_name" "$backup_dir"
