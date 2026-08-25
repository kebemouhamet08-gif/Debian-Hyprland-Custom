#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$repo_dir/config/mpvpaper-engine"
install_dir="$HOME/.local/lib/mpvpaper-engine"
bin_dir="$HOME/.local/bin"
desktop_dir="$HOME/.local/share/applications"
systemd_dir="$HOME/.config/systemd/user"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$HOME/.config/mpvpaper-engine-backup-$timestamp"

for command_name in mpvpaper ffmpeg ffmpegthumbnailer ffprobe python3 systemctl systemd-run hyprctl yt-dlp; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Dépendance manquante : %s\n' "$command_name" >&2
        exit 1
    fi
done

python3 -c "import gi; gi.require_version('Adw', '1'); gi.require_version('Gtk', '4.0'); gi.require_version('WebKit', '6.0')" \
    2>/dev/null || {
        printf 'Dépendances GTK manquantes : python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 ou gir1.2-webkit-6.0.\n' >&2
        exit 1
    }

mkdir -p "$backup_dir" "$install_dir" "$bin_dir" "$desktop_dir" "$systemd_dir"
for path in "$install_dir" "$bin_dir/mpvpaper-engine" "$bin_dir/mpvpaper-enginectl" \
    "$bin_dir/mpvpaper-engine-toggle" \
    "$desktop_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop" \
    "$systemd_dir/mpvpaper-engine-prefetch.service" \
    "$systemd_dir/mpvpaper-engine-prefetch.timer"; do
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
install -m 0644 "$source_dir/mpvpaper-engine-prefetch.service" \
    "$systemd_dir/mpvpaper-engine-prefetch.service"
install -m 0644 "$source_dir/mpvpaper-engine-prefetch.timer" \
    "$systemd_dir/mpvpaper-engine-prefetch.timer"
ln -sfn "$install_dir/mpvpaper-engine.py" "$bin_dir/mpvpaper-engine"
ln -sfn "$install_dir/mpvpaper-enginectl.py" "$bin_dir/mpvpaper-enginectl"
ln -sfn "$install_dir/mpvpaper-engine-toggle" "$bin_dir/mpvpaper-engine-toggle"

mkdir -p "$HOME/Pictures/Wallpapers/Live"
update-desktop-database "$desktop_dir" 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user disable mpvpaper-engine-prefetch.service >/dev/null 2>&1 || true
systemctl --user enable --now mpvpaper-engine-prefetch.timer >/dev/null
systemctl --user start --no-block mpvpaper-engine-prefetch.service || true

printf 'MPVpaper Engine installé. Sauvegarde : %s\n' "$backup_dir"
printf 'Lancez-le avec : %s\n' "$bin_dir/mpvpaper-engine"
