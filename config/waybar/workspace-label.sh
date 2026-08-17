#!/usr/bin/env bash

set -u

workspace_id="${1:?numéro de bureau manquant}"

clients="$(hyprctl clients -j 2>/dev/null || printf '[]')"
active_workspace="$(hyprctl activeworkspace -j 2>/dev/null | jq -r '.id // 0')"

icons="$(
    jq -r --argjson workspace "$workspace_id" \
        --argjson active "$active_workspace" '
        [
            .[]
            | select(
                (.workspace.id == $workspace)
                or
                (
                    $workspace == $active
                    and (.workspace.name | startswith("special:"))
                    and .workspace.name != "special:minimized"
                    and (.hidden == false)
                )
              )
            | (.class // "" | ascii_downcase)
            | if test("firefox") then ""
              elif test("google-chrome|chromium|brave") then ""
              elif test("code") then "󰨞"
              elif test("kitty|alacritty|wezterm") then ""
              elif test("thunar|nautilus|dolphin") then ""
              elif test("discord|vesktop") then ""
              elif test("spotify") then ""
              elif test("steam") then ""
              elif test("obsproject|obs") then "󰐌"
              else ""
              end
        ]
        | unique
        | join(" ")
    ' <<<"$clients"
)"

if [ -z "$icons" ]; then
    label="$workspace_id"
else
    label="$icons"
fi

if [ "$active_workspace" = "$workspace_id" ]; then
    css_class="active"
else
    css_class="inactive"
fi

jq -cn --arg text "$label" --arg class "$css_class" \
    --arg tooltip "Bureau $workspace_id" \
    '{text: $text, class: $class, tooltip: $tooltip}'
