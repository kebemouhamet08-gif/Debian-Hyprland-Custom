#!/usr/bin/env bash

set -u

# Caelestia replaces Waybar in the v2 session. Stop only the running process;
# the v1 files stay installed and can be selected again at any time.
pkill -x waybar 2>/dev/null || true

# On Debian, Nix applications cannot use the host Mesa driver directly.
# nixGLIntel bridges the Nix Qt/Quickshell runtime to the Intel GPU driver.
if [ -x "$HOME/.nix-profile/bin/nixGLIntel" ] && \
   [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
    exec "$HOME/.nix-profile/bin/nixGLIntel" \
        "$HOME/.nix-profile/bin/caelestia" shell -d
fi

# Keep a fallback for systems where the Nix package already has working GL.
if [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
    exec "$HOME/.nix-profile/bin/caelestia" shell -d
fi

if command -v caelestia >/dev/null 2>&1; then
    exec caelestia shell -d
fi

if command -v qs >/dev/null 2>&1; then
    exec qs -c caelestia
fi

command -v notify-send >/dev/null 2>&1 && notify-send \
    "Deblestia Shell v2" \
    "Caelestia indisponible : installez caelestia-cli et Quickshell git."
