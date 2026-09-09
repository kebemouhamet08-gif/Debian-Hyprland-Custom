#!/usr/bin/env bash

# Génère la palette commune des Waybars depuis le fond d'écran courant.
set -u

wallpaper="$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
wallust_colors="$HOME/.config/waybar/wallust/colors-waybar.css"
panel_colors="$HOME/.config/waybar/panel-colors.css"
state_file="$HOME/.config/waybar/.panel-state"
skip_wallust=0
reload_waybars=0
no_start=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --from-wallust) skip_wallust=1 ;;
        --reload) reload_waybars=1 ;;
        --no-start) no_start=1 ;;
        --wallpaper)
            [ "$#" -ge 2 ] || exit 2
            wallpaper="$2"
            shift
            ;;
        *) exit 2 ;;
    esac
    shift
done

if [ "$skip_wallust" -eq 0 ] && command -v wallust >/dev/null 2>&1 && \
        [ -s "$wallpaper" ]; then
    wallust run -s "$wallpaper" >/dev/null 2>&1 || true
fi

css_color() {
    sed -n "s/^[[:space:]]*@define-color $1[[:space:]]\+\([^;]*\);.*/\1/p" \
        "$wallust_colors" 2>/dev/null | tail -n 1
}

hex_to_rgb() {
    local hex="${1#\#}"
    printf '%d, %d, %d' "0x${hex:0:2}" "0x${hex:2:2}" "0x${hex:4:2}"
}

# Teinte le verre avec la couleur dominante tout en gardant assez de contraste.
mix_hex_rgb() {
    local base="${1#\#}" tint="${2#\#}" tint_percent="${3:-18}"
    local base_percent=$((100 - tint_percent)) channel mixed values=()
    for channel in 0 2 4; do
        mixed=$(( (16#${base:channel:2} * base_percent + \
                   16#${tint:channel:2} * tint_percent) / 100 ))
        values+=("$mixed")
    done
    printf '%d, %d, %d' "${values[@]}"
}

accent="$(css_color color13)"
text="$(css_color foreground)"
background="$(css_color background)"
muted="$(css_color color8)"
accent="${accent:-#d4cdd8}"
text="${text:-#f3edf2}"
background="${background:-#0e0f16}"
muted="${muted:-#b8aeb8}"
accent_rgb="$(hex_to_rgb "$accent")"
background_rgb="$(mix_hex_rgb "$background" "$accent" 18)"
opacity="$(sed -n 's/^opacity=//p' "$state_file" 2>/dev/null | tail -n 1)"
opacity="${opacity:-0.86}"
temporary="$(mktemp "$HOME/.config/waybar/.panel-colors.XXXXXX")"
trap 'rm -f "$temporary"' EXIT

{
    printf '/* Généré depuis le fond actuel par WaybarWallpaperSync.sh. */\n'
    printf '@define-color glass rgba(%s, %s);\n' "$background_rgb" "$opacity"
    printf '@define-color glass_hover rgba(%s, 0.30);\n' "$accent_rgb"
    printf '@define-color accent %s;\n' "$accent"
    printf '@define-color accent_soft rgba(%s, 0.42);\n' "$accent_rgb"
    printf '@define-color text %s;\n' "$text"
    printf '@define-color muted %s;\n' "$muted"
} >"$temporary"

if ! cmp -s "$temporary" "$panel_colors"; then
    mv "$temporary" "$panel_colors"
    trap - EXIT
fi

system_theme_sync="$HOME/.config/hypr/UserScripts/DeblestiaSystemThemeSync.sh"
if [ -x "$system_theme_sync" ]; then
    "$system_theme_sync" >/dev/null 2>&1 || true
fi

if [ "$reload_waybars" -eq 1 ]; then
    pkill -SIGUSR2 -x waybar >/dev/null 2>&1 || true
fi

if [ "$no_start" -eq 1 ] || [ "$reload_waybars" -eq 1 ]; then
    exit 0
fi

exec waybar
