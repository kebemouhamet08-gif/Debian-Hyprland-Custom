#!/usr/bin/env bash

set -u

stats_class="deblestia-system-stats"

if hyprctl clients -j 2>/dev/null | jq -e --arg class "$stats_class" \
        '.[] | select(.class == $class)' >/dev/null; then
    hyprctl dispatch closewindow "class:^(${stats_class})$"
else
    kitty --class "$stats_class" --title "System Overview" -e btop \
        >/dev/null 2>&1 &
fi
