#!/usr/bin/env bash

set -u

state_file="$HOME/.cache/caelestia-v2-display-profile"
legacy_state_file="$HOME/.cache/.hyprsunset_state"
gamma="${CAELESTIA_DISPLAY_GAMMA:-70}"
temperature="${CAELESTIA_DISPLAY_TEMPERATURE:-6500}"
service="caelestia-v2-display-profile.service"

if ! command -v hyprsunset >/dev/null 2>&1; then
    notify-send -u critical "Profil d'affichage indisponible" \
        "hyprsunset n'est pas installé" 2>/dev/null || true
    exit 1
fi

stop_filter() {
    systemctl --user stop "$service" >/dev/null 2>&1 || true
    pkill -x hyprsunset 2>/dev/null || true
}

enable_oled() {
    if systemctl --user is-active --quiet "$service" && \
       [ "$(cat "$state_file" 2>/dev/null)" = "oled" ]; then
        return
    fi

    stop_filter
    printf 'off\n' >"$legacy_state_file"
    systemd-run --user --quiet --collect --unit="$service" \
        hyprsunset --temperature "$temperature" --gamma "$gamma" \
        --gamma_max 100
    printf 'oled\n' >"$state_file"
}

disable_oled() {
    stop_filter
    hyprsunset --identity >/dev/null 2>&1 &
    identity_pid=$!
    sleep 0.3
    kill "$identity_pid" 2>/dev/null || true
    printf 'neutral\n' >"$state_file"
}

case "${1:-oled}" in
    oled)
        enable_oled
        ;;
    neutral)
        disable_oled
        ;;
    toggle)
        if [ "$(cat "$state_file" 2>/dev/null)" = "oled" ]; then
            disable_oled
            notify-send -u low "Profil d'affichage" "Couleurs neutres" 2>/dev/null || true
        else
            enable_oled
            notify-send -u low "Profil d'affichage" "Contraste OLED modéré" 2>/dev/null || true
        fi
        ;;
    *)
        printf 'Usage : %s [oled|neutral|toggle]\n' "$0" >&2
        exit 2
        ;;
esac
