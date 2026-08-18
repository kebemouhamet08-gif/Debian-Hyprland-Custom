#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$repo_dir/config/mpvpaper-engine"
install_dir="$HOME/.local/lib/mpvpaper-engine"
bin_dir="$HOME/.local/bin"
desktop_dir="$HOME/.local/share/applications"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$HOME/.config/mpvpaper-engine-backup-$timestamp"

for command_name in mpvpaper ffmpegthumbnailer ffprobe python3 systemd-run hyprctl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Dépendance manquante : %s\n' "$command_name" >&2
        exit 1
    fi
done

python3 -c "import gi; gi.require_version('Adw', '1'); gi.require_version('Gtk', '4.0')" \
    2>/dev/null || {
        printf 'Dépendances GTK manquantes : python3-gi, gir1.2-gtk-4.0 ou gir1.2-adw-1.\n' >&2
        exit 1
    }

mkdir -p "$backup_dir" "$install_dir" "$bin_dir" "$desktop_dir"
for path in "$install_dir" "$bin_dir/mpvpaper-engine" "$bin_dir/mpvpaper-enginectl" \
    "$bin_dir/mpvpaper-engine-toggle" \
    "$desktop_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a --parents "$path" "$backup_dir/"
    fi
done

install -m 0755 "$source_dir/mpvpaper-engine.py" "$install_dir/mpvpaper-engine.py"
install -m 0755 "$source_dir/mpvpaper-enginectl.py" "$install_dir/mpvpaper-enginectl.py"
install -m 0755 "$source_dir/mpvpaper-engine-toggle" "$install_dir/mpvpaper-engine-toggle"
install -m 0755 "$source_dir/install-sddm-background.sh" "$install_dir/install-sddm-background.sh"
install -m 0644 "$source_dir/sddm-background.patch" "$install_dir/sddm-background.patch"
install -m 0644 "$source_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop" \
    "$desktop_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop"
ln -sfn "$install_dir/mpvpaper-engine.py" "$bin_dir/mpvpaper-engine"
ln -sfn "$install_dir/mpvpaper-enginectl.py" "$bin_dir/mpvpaper-enginectl"
ln -sfn "$install_dir/mpvpaper-engine-toggle" "$bin_dir/mpvpaper-engine-toggle"

mkdir -p "$HOME/Pictures/Wallpapers/Live"
update-desktop-database "$desktop_dir" 2>/dev/null || true

printf 'MPVpaper Engine installé. Sauvegarde : %s\n' "$backup_dir"
printf 'Lancez-le avec : %s\n' "$bin_dir/mpvpaper-engine"
