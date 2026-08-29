#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$repo_dir/config/mirrorbridge"
manifest="$source_dir/Cargo.toml"
release_binary="$source_dir/target/release/mirrorbridge"
bin_dir="${HOME}/.local/bin"
desktop_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
binary_target="$bin_dir/mirrorbridge"
desktop_target="$desktop_dir/io.github.kebemouhamet08.MirrorBridge.desktop"

usage() {
    printf 'Usage : %s [check|build|install|launch|restore]\n' "$0"
}

check() {
    local missing=0
    for command in cargo pkg-config adb; do
        if command -v "$command" >/dev/null 2>&1; then
            printf 'OK       %s\n' "$command"
        else
            printf 'MANQUANT %s\n' "$command"
            missing=1
        fi
    done

    if pkg-config --exists gtk4; then
        printf 'OK       GTK %s\n' "$(pkg-config --modversion gtk4)"
    else
        printf 'MANQUANT GTK4 (paquet libgtk-4-dev)\n'
        missing=1
    fi

    if command -v scrcpy >/dev/null 2>&1; then
        printf 'OK       scrcpy\n'
    else
        printf 'OPTION   scrcpy absent : utilisez la version officielle https://github.com/Genymobile/scrcpy/blob/master/doc/linux.md\n'
    fi
    if command -v uxplay >/dev/null 2>&1; then
        printf 'OK       uxplay\n'
    else
        printf 'OPTION   uxplay absent : sudo apt install uxplay (https://github.com/FDH2/UxPlay)\n'
    fi
    return "$missing"
}

build() {
    check
    cargo build --release --manifest-path "$manifest"
}

install_app() {
    build
    mkdir -p "$bin_dir" "$desktop_dir"
    install -m 0755 "$release_binary" "$binary_target"
    install -m 0644 "$source_dir/io.github.kebemouhamet08.MirrorBridge.desktop" "$desktop_target"
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
    printf 'MirrorBridge installé. Lancez : %s\n' "$binary_target"
}

launch() {
    if [ -x "$binary_target" ]; then
        exec "$binary_target"
    fi
    cargo run --manifest-path "$manifest"
}

restore() {
    rm -f "$binary_target" "$desktop_target"
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
    printf 'MirrorBridge a été retiré du compte utilisateur.\n'
}

case "${1:-install}" in
    check) check ;;
    build) build ;;
    install) install_app ;;
    launch) launch ;;
    restore) restore ;;
    *) usage; exit 2 ;;
esac
