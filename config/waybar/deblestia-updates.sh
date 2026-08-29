#!/usr/bin/env bash

set -u

count="$(apt list --upgradable 2>/dev/null | awk 'NR > 1 { total++ } END { print total + 0 }')"

if [ "$count" -gt 0 ]; then
    css_class="pending"
    tooltip="$count mise(s) à jour disponible(s) · Cliquer pour ouvrir APT"
else
    css_class="current"
    tooltip="Système à jour"
fi

jq -cn --arg text "󰏔 $count" --arg class "$css_class" \
    --arg tooltip "$tooltip" \
    '{text: $text, class: $class, tooltip: $tooltip}'
