#!/usr/bin/env bash

set -euo pipefail

waybar_dir="${XDG_CONFIG_HOME:-$HOME/.config}/waybar"
output="$waybar_dir/theme-overrides.css"
preset="${1:-}"

if [ -z "$preset" ]; then
    preset="$(
        printf '%s\n' \
            'Rose · Deblestia' \
            'Tokyo · nuit bleue' \
            'Nord · glace' \
            'Gruvbox · terre' \
            'Mono · minimal' \
            'Wallpaper · dynamique' |
            rofi -dmenu -i -p 'Palette Nova' \
                -theme "$HOME/.config/rofi/DebianGlass.rasi"
    )"
fi

case "$preset" in
    rose|Rose*)
        label="Rose"
        palette='@define-color nova_bg rgba(34, 28, 27, 0.88);
@define-color nova_bg_soft rgba(50, 40, 37, 0.74);
@define-color nova_hover rgba(117, 89, 76, 0.72);
@define-color nova_accent #e4b79f;
@define-color nova_accent_strong #f2c7ad;
@define-color nova_text #f8eee8;
@define-color nova_muted #cbbab0;
@define-color nova_good #a8d8ad;
@define-color nova_warning #f1c27d;
@define-color nova_danger #ff7f87;'
        ;;
    tokyo|Tokyo*)
        label="Tokyo"
        palette='@define-color nova_bg rgba(21, 24, 42, 0.91);
@define-color nova_bg_soft rgba(31, 35, 58, 0.78);
@define-color nova_hover rgba(61, 66, 104, 0.78);
@define-color nova_accent #7aa2f7;
@define-color nova_accent_strong #bb9af7;
@define-color nova_text #c0caf5;
@define-color nova_muted #8990b3;
@define-color nova_good #9ece6a;
@define-color nova_warning #e0af68;
@define-color nova_danger #f7768e;'
        ;;
    nord|Nord*)
        label="Nord"
        palette='@define-color nova_bg rgba(38, 46, 59, 0.91);
@define-color nova_bg_soft rgba(49, 59, 75, 0.79);
@define-color nova_hover rgba(67, 76, 94, 0.82);
@define-color nova_accent #88c0d0;
@define-color nova_accent_strong #8fbcbb;
@define-color nova_text #eceff4;
@define-color nova_muted #aebacb;
@define-color nova_good #a3be8c;
@define-color nova_warning #ebcb8b;
@define-color nova_danger #bf616a;'
        ;;
    gruvbox|Gruvbox*)
        label="Gruvbox"
        palette='@define-color nova_bg rgba(40, 40, 40, 0.92);
@define-color nova_bg_soft rgba(60, 56, 54, 0.80);
@define-color nova_hover rgba(80, 73, 69, 0.82);
@define-color nova_accent #d79921;
@define-color nova_accent_strong #fabd2f;
@define-color nova_text #ebdbb2;
@define-color nova_muted #bdae93;
@define-color nova_good #b8bb26;
@define-color nova_warning #fe8019;
@define-color nova_danger #fb4934;'
        ;;
    mono|Mono*)
        label="Mono"
        palette='@define-color nova_bg rgba(18, 18, 20, 0.92);
@define-color nova_bg_soft rgba(31, 31, 34, 0.82);
@define-color nova_hover rgba(67, 67, 72, 0.78);
@define-color nova_accent #d5d5d8;
@define-color nova_accent_strong #ffffff;
@define-color nova_text #eeeeef;
@define-color nova_muted #a0a0a5;
@define-color nova_good #c7ddc9;
@define-color nova_warning #e5d2ad;
@define-color nova_danger #e4a6aa;'
        ;;
    wallpaper|Wallpaper*)
        label="Wallpaper"
        palette='@define-color nova_bg @glass;
@define-color nova_bg_soft @glass;
@define-color nova_hover @glass_hover;
@define-color nova_accent @accent;
@define-color nova_accent_strong @accent;
@define-color nova_text @text;
@define-color nova_muted @muted;
@define-color nova_good #a8d8ad;
@define-color nova_warning #f1c27d;
@define-color nova_danger #ff7f87;'
        ;;
    '') exit 0 ;;
    *)
        printf 'Palette inconnue : %s\n' "$preset" >&2
        exit 2
        ;;
esac

temporary="$(mktemp "$waybar_dir/.theme-overrides.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
printf '%s\n%s\n' '/* Généré par deblestia-theme.sh. */' "$palette" >"$temporary"
mv "$temporary" "$output"
trap - EXIT

pkill -SIGUSR2 -x waybar 2>/dev/null || true
notify-send "Deblestia Nova" "Palette $label activée"
