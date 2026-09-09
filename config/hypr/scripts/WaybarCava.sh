#!/usr/bin/env bash
# WaybarCava.sh — instances indépendantes par barre/sortie.
# Original concept by JaKooLit; cette variante sécurise le multi-écran.

set -euo pipefail

# Ensure cava exists
if ! command -v cava >/dev/null 2>&1; then
  echo "cava not found in PATH" >&2
  exit 1
fi

# 0..7 → ▁▂▃▄▅▆▇█
bar="▁▂▃▄▅▆▇█"
dict="s/;//g"
bar_length=${#bar}
for ((i = 0; i < bar_length; i++)); do
  dict+=";s/$i/${bar:$i:1}/g"
done

# Une clé différente empêche une barre de tuer le visualiseur d'une autre.
instance="${1:-default}"
instance="$(printf '%s' "$instance" | tr -c '[:alnum:]_.-' '_')"
runtime_root="${XDG_RUNTIME_DIR:-/tmp}/deblestia/waybar-cava"
mkdir -p "$runtime_root"
pidfile="$runtime_root/${instance}.pid"
if [[ -f "$pidfile" ]]; then
  oldpid="$(<"$pidfile")"
  if [[ "$oldpid" =~ ^[0-9]+$ ]] && kill -0 "$oldpid" 2>/dev/null &&
      tr '\0' ' ' <"/proc/$oldpid/cmdline" 2>/dev/null | grep -Fq 'WaybarCava.sh'; then
    kill "$oldpid" 2>/dev/null || true
  fi
fi
printf '%d\n' $$ >"$pidfile"

# Unique temp config + cleanup on exit
config_file="$(mktemp "$runtime_root/${instance}.XXXXXX.conf")"
cleanup() {
  local current_pid
  rm -f "$config_file"
  current_pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ "$current_pid" = "$$" ]]; then
    rm -f "$pidfile"
  fi
}
trap cleanup EXIT INT TERM

cat >"$config_file" <<EOF
[general]
framerate = 30
bars = 8

[input]
method = pulse
source = auto

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 7
EOF

# Stream cava output and translate digits 0..7 to bar glyphs.
cava -p "$config_file" | sed -u "$dict"
