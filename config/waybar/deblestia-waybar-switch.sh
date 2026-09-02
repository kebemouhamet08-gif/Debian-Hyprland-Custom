#!/usr/bin/env bash

set -euo pipefail

waybar_dir="${XDG_CONFIG_HOME:-$HOME/.config}/waybar"
variant="${1:-}"

if [ -z "$variant" ]; then
    variant="$(
        printf '%s\n' 'Nova Lite · îlots horizontaux' 'Bar · barre verticale' |
            rofi -dmenu -i -p 'Variante Deblestia' \
                -theme "$HOME/.config/rofi/DebianGlass.rasi"
    )"
fi

case "$variant" in
    nova|Nova*)
        config_name='[Deblestia] Nova Lite'
        style_name='[Deblestia] Nova Lite.css'
        ;;
    bar|Bar*)
        config_name='[Deblestia] Bar'
        style_name='[Deblestia] Bar.css'
        ;;
    '') exit 0 ;;
    *)
        printf 'Variante inconnue : %s\n' "$variant" >&2
        exit 2
        ;;
esac

ln -sfn "$waybar_dir/configs/$config_name" "$waybar_dir/config"
ln -sfn "$waybar_dir/styles/$style_name" "$waybar_dir/style.css"
"$HOME/.config/hypr/scripts/desktop-shell-mode.sh" "$config_name" &
notify-send "Deblestia" "$config_name activé"
