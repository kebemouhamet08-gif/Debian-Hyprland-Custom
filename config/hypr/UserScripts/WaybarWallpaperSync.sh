#!/usr/bin/env bash

# Génère la palette commune des Waybars depuis le fond d'écran courant.
set -u

wallpaper="$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
wallust_colors="$HOME/.config/waybar/wallust/colors-waybar.css"
panel_colors="$HOME/.config/waybar/panel-colors.css"
state_file="$HOME/.config/waybar/.panel-state"
skip_wallust=0
reload_waybars=0

for option in "$@"; do
    case "$option" in
        --from-wallust) skip_wallust=1 ;;
        --reload) reload_waybars=1 ;;
        --no-start) ;;
        *) exit 2 ;;
    esac
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

accent="$(css_color color13)"
text="$(css_color foreground)"
background="$(css_color background)"
muted="$(css_color color8)"
accent="${accent:-#d4cdd8}"
text="${text:-#f3edf2}"
background="${background:-#0e0f16}"
muted="${muted:-#b8aeb8}"
accent_rgb="$(hex_to_rgb "$accent")"
background_rgb="$(hex_to_rgb "$background")"
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

if [ "$reload_waybars" -eq 1 ]; then
    pkill -SIGUSR2 -x waybar >/dev/null 2>&1 || true
fi

if [[ " $* " == *" --no-start "* ]] || [ "$reload_waybars" -eq 1 ]; then
    exit 0
fi

exec waybar
