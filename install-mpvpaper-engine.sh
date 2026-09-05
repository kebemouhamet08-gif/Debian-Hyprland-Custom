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

check_dependencies() {
    local command_name failed=0
    for command_name in mpvpaper ffmpeg ffmpegthumbnailer ffprobe python3 systemctl systemd-run hyprctl; do
        if command -v "$command_name" >/dev/null 2>&1; then
            printf 'OK       %s\n' "$command_name"
        else
            printf 'MANQUANT %s\n' "$command_name" >&2
            failed=1
        fi
    done
    if command -v deno >/dev/null 2>&1 || [ -x "$HOME/.local/bin/deno" ]; then
        printf 'OK       deno (défis JavaScript YouTube)\n'
    else
        printf 'RECOMMANDÉ deno (la méthode yt-dlp classique reste disponible)\n'
    fi
    if command -v steamcmd >/dev/null 2>&1; then
        printf 'OK       steamcmd (import forcé Steam Workshop)\n'
    else
        printf 'OPTIONNEL steamcmd (sinon API Steam, contenu local ou aperçu)\n'
    fi

    if python3 -c "import gi; gi.require_version('Adw', '1'); gi.require_version('Gtk', '4.0'); gi.require_version('WebKit', '6.0')" \
        2>/dev/null; then
        printf 'OK       GTK4, Libadwaita et WebKitGTK 6.0\n'
    else
        printf 'MANQUANT python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 ou gir1.2-webkit-6.0\n' >&2
        failed=1
    fi
    return "$failed"
}

action="${1:-install}"
if [ "$action" = check ]; then
    check_dependencies
    exit
fi
if [ "$action" != install ]; then
    printf 'Usage : %s [check|install]\n' "$0" >&2
    exit 2
fi

check_dependencies

mkdir -p "$backup_dir" "$install_dir" "$bin_dir" "$desktop_dir" "$systemd_dir"
for path in "$install_dir" "$bin_dir/mpvpaper-engine" "$bin_dir/mpvpaper-enginectl" \
    "$bin_dir/mpvpaper-engine-toggle" \
    "$bin_dir/mpvpaper-engine-waybar" \
    "$bin_dir/mpvpaper-engine-quick-menu" \
    "$bin_dir/mpvpaper-workshop" \
    "$desktop_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop" \
    "$systemd_dir/mpvpaper-engine-prefetch.service" \
    "$systemd_dir/mpvpaper-engine-prefetch.timer"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a --parents "$path" "$backup_dir/"
    fi
done

if [ "${MPVPAPER_ENGINE_SKIP_DOWNLOADER_SETUP:-0}" != 1 ]; then
    printf 'Configuration de l’environnement yt-dlp privé…\n'
    if python3 -m venv "$install_dir/.venv" \
        && "$install_dir/.venv/bin/python" -m pip install -U pip \
        && "$install_dir/.venv/bin/python" -m pip install -U --pre \
            'yt-dlp[default,curl-cffi]' yt-dlp-ejs; then
        printf 'OK       environnement yt-dlp privé\n'
    else
        printf 'AVERTISSEMENT environnement privé indisponible; yt-dlp utilisateur utilisé.\n' >&2
    fi
fi

install -m 0755 "$source_dir/mpvpaper-engine.py" "$install_dir/mpvpaper-engine.py"
install -m 0755 "$source_dir/mpvpaper-engine-v2.py" "$install_dir/mpvpaper-engine-v2.py"
install -m 0755 "$source_dir/mpvpaper-engine-service.py" "$install_dir/mpvpaper-engine-service.py"
install -m 0755 "$source_dir/mpvpaper-engine-launcher" "$install_dir/mpvpaper-engine-launcher"
install -m 0755 "$source_dir/mpvpaper_download.py" "$install_dir/mpvpaper_download.py"
install -m 0755 "$source_dir/mpvpaper-enginectl.py" "$install_dir/mpvpaper-enginectl.py"
install -m 0755 "$source_dir/mpvpaper-engine-toggle" "$install_dir/mpvpaper-engine-toggle"
install -m 0755 "$source_dir/mpvpaper-engine-waybar.py" "$install_dir/mpvpaper-engine-waybar.py"
install -m 0755 "$source_dir/mpvpaper-engine-quick-menu" "$install_dir/mpvpaper-engine-quick-menu"
mkdir -p "$install_dir/mpvpaper_engine"
for module in "$source_dir"/mpvpaper_engine/*.py; do
    install -m 0644 "$module" "$install_dir/mpvpaper_engine/$(basename "$module")"
done
install -m 0755 "$source_dir/install-sddm-background.sh" "$install_dir/install-sddm-background.sh"
install -m 0644 "$source_dir/sddm-background.patch" "$install_dir/sddm-background.patch"
install -m 0644 "$source_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop" \
    "$desktop_dir/io.github.kebemouhamet08.MPVpaperEngine.desktop"
install -m 0644 "$source_dir/mpvpaper-engine-prefetch.service" \
    "$systemd_dir/mpvpaper-engine-prefetch.service"
install -m 0644 "$source_dir/mpvpaper-engine-prefetch.timer" \
    "$systemd_dir/mpvpaper-engine-prefetch.timer"
install -m 0644 "$source_dir/mpvpaper-engine.service" \
    "$systemd_dir/mpvpaper-engine.service"
ln -sfn "$install_dir/mpvpaper-engine-launcher" "$bin_dir/mpvpaper-engine"
ln -sfn "$install_dir/mpvpaper-enginectl.py" "$bin_dir/mpvpaper-enginectl"
ln -sfn "$install_dir/mpvpaper-engine-toggle" "$bin_dir/mpvpaper-engine-toggle"
ln -sfn "$install_dir/mpvpaper_download.py" "$bin_dir/mpvpaper-workshop"
ln -sfn "$install_dir/mpvpaper-engine-waybar.py" "$bin_dir/mpvpaper-engine-waybar"
ln -sfn "$install_dir/mpvpaper-engine-quick-menu" "$bin_dir/mpvpaper-engine-quick-menu"

mkdir -p "$HOME/Pictures/Wallpapers/Live"
update-desktop-database "$desktop_dir" 2>/dev/null || true
if [ "${MPVPAPER_ENGINE_SKIP_SYSTEMD:-0}" != 1 ]; then
    systemctl --user daemon-reload
    systemctl --user enable --now mpvpaper-engine.service >/dev/null
    systemctl --user disable mpvpaper-engine-prefetch.service >/dev/null 2>&1 || true
    systemctl --user enable --now mpvpaper-engine-prefetch.timer >/dev/null
    systemctl --user start --no-block mpvpaper-engine-prefetch.service || true
fi

printf 'MPVpaper Engine installé. Sauvegarde : %s\n' "$backup_dir"
printf 'Lancez-le avec : %s\n' "$bin_dir/mpvpaper-engine"
