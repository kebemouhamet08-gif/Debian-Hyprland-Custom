#!/usr/bin/env bash

# Overview Deblestia : Quickshell en priorité, AGS en fallback.
set -euo pipefail

if command -v qs >/dev/null 2>&1; then
    if qs ipc -c overview call overview toggle >/dev/null 2>&1; then
        exit 0
    fi
    qs -c overview >/dev/null 2>&1 &
    sleep 0.6
    if qs ipc -c overview call overview toggle >/dev/null 2>&1; then
        exit 0
    fi
fi

if command -v ags >/dev/null 2>&1; then
    pkill rofi 2>/dev/null || true
    if ags -t overview >/dev/null 2>&1; then
        exit 0
    fi
    ags >/dev/null 2>&1 &
    sleep 0.6
    if ags -t overview >/dev/null 2>&1; then
        exit 0
    fi
fi

notify-send -u low "Overview" "Quickshell Overview et AGS sont indisponibles" \
    2>/dev/null || true
exit 1
