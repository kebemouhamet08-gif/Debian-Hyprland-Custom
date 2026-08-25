#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
state_dir="$config_home/debian-next-v3"
state_file="$state_dir/state"
history_file="$state_dir/history.log"
manifest="$repo_dir/config/v3/components.tsv"
app_source="$repo_dir/config/v3/device-center.py"
cli_source="$repo_dir/config/v3/periphx.py"
desktop_source="$repo_dir/config/v3/io.github.kebemouhamet08.DebianNextV3Devices.desktop"
service_source="$repo_dir/config/v3/pericored/pericored.service"
install_dir="$HOME/.local/lib/debian-next-v3"
bin_dir="$HOME/.local/bin"
desktop_dir="$HOME/.local/share/applications"
app_target="$install_dir/device-center.py"
cli_target="$install_dir/periphx.py"
app_command="$bin_dir/periphx"
launcher_target="$install_dir/periphx-launcher"
legacy_command="$bin_dir/debian-next-v3-devices"
desktop_target="$desktop_dir/io.github.kebemouhamet08.PeriphX.desktop"
shell_config="$HOME/.zshrc"
pericore_manifest="$repo_dir/config/v3/pericored/Cargo.toml"
pericore_binary="$repo_dir/config/v3/pericored/target/release/pericored"
pericore_target="$install_dir/pericored"
pericore_command="$bin_dir/pericored"
service_dir="$config_home/systemd/user"
service_target="$service_dir/pericored.service"
dry_run=0
path_marker="$state_dir/path-added-by-installer"

usage() {
    cat <<'EOF'
Usage : ./install-v3.sh [check|install|dev|launch|status|restore] [--dry-run]

  check       vérifie le manifeste et les prérequis V3
  install     initialise l'état isolé de la V3
    dev         utilise directement le code source PeriphX du dépôt
    launch      lance le centre de contrôle matériel
  status      affiche l'état V3
  restore     retire l'état V3 sans toucher à V1 ou V2
  --dry-run   affiche les écritures prévues
EOF
}

log_action() {
    printf '[simulation] %s\n' "$*"
}

check_v3() {
    local failed=0
    if [ -f "$manifest" ]; then
        printf 'OK       manifeste V3\n'
    else
        printf 'MANQUANT manifeste : %s\n' "$manifest" >&2
        failed=1
    fi
    for source in "$app_source" "$cli_source" "$desktop_source" "$service_source"; do
        if [ -f "$source" ]; then
            printf 'OK       %s\n' "$(basename "$source")"
        else
            printf 'MANQUANT %s\n' "$source" >&2
            failed=1
        fi
    done
    if [ -f "$pericore_manifest" ]; then
        printf 'OK       pericored Rust\n'
    else
        printf 'MANQUANT manifeste pericored : %s\n' "$pericore_manifest" >&2
        failed=1
    fi
    if command -v hyprctl >/dev/null 2>&1 || command -v Hyprland >/dev/null 2>&1; then
        printf 'OK       Hyprland\n'
    else
        printf 'INFO     Hyprland non détecté (installation différée)\n'
    fi
    return "$failed"
}

install_v3() {
    if ((dry_run)); then
        log_action "mkdir -p $state_dir"
        log_action "installer $app_source vers $app_target"
        log_action "installer $cli_source vers $cli_target"
        log_action "installer le lanceur $app_command"
        log_action "installer $desktop_source vers $desktop_target"
        log_action "compiler pericored avec cargo"
        log_action "installer pericored vers $pericore_target"
        log_action "lier $pericore_command vers $pericore_target"
        log_action "installer et activer $service_target"
        log_action "initialiser $state_file et $history_file"
        return
    fi
    mkdir -p "$state_dir" "$install_dir" "$bin_dir" "$desktop_dir" "$service_dir"
    build_pericored
    install -m 0755 "$app_source" "$app_target"
    install -m 0755 "$cli_source" "$cli_target"
    write_launcher
    ln -sfn "$launcher_target" "$app_command"
    ln -sfn "$launcher_target" "$legacy_command"
    ln -sfn "$cli_target" "$bin_dir/periphx-cli"
    install -m 0644 "$service_source" "$service_target"
    enable_pericored
    ensure_local_bin_path
    install -m 0644 "$desktop_source" "$desktop_target"
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
    if [ ! -f "$state_file" ]; then
        printf 'version=3\ncreated_at=%s\n' "$(date +%Y%m%d-%H%M%S)" >"$state_file"
        printf '%s\tinstall\n' "$(date +%Y%m%d-%H%M%S)" >>"$history_file"
    fi
    printf 'Socle Debian Next V3 initialisé : %s\n' "$state_dir"
    printf 'Lancement direct : %s\n' "$app_target"
    printf 'Commande PeriphX : %s\n' "$app_command"
    printf 'Si nécessaire : export PATH="$HOME/.local/bin:$PATH"\n'
}

dev_v3() {
    mkdir -p "$state_dir" "$install_dir" "$bin_dir" "$desktop_dir" "$service_dir"
    chmod +x "$app_source"
    ln -sfn "$app_source" "$app_target"
    write_launcher
    ln -sfn "$launcher_target" "$app_command"
    ln -sfn "$launcher_target" "$legacy_command"
    install -m 0755 "$cli_source" "$cli_target"
    ln -sfn "$cli_target" "$bin_dir/periphx-cli"
    build_pericored
    install -m 0644 "$service_source" "$service_target"
    enable_pericored
    install -m 0644 "$desktop_source" "$desktop_target"
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
    ensure_local_bin_path
    printf 'Mode développement PeriphX activé.\n'
    printf 'Source suivie directement : %s\n' "$app_source"
    printf 'Lancement : %s\n' "$app_command"
}

build_pericored() {
    if ! command -v cargo >/dev/null 2>&1; then
        printf 'INFO     cargo absent : pericored non compilé\n'
        return
    fi
    cargo build --release --manifest-path "$pericore_manifest"
    install -m 0755 "$pericore_binary" "$pericore_target.new"
    mv -f "$pericore_target.new" "$pericore_target"
    ln -sfn "$pericore_target" "$pericore_command"
}

enable_pericored() {
    if ! command -v systemctl >/dev/null 2>&1; then
        printf 'INFO     systemd utilisateur absent : lancez %s manuellement\n' "$pericore_command"
        return
    fi
    if ! systemctl --user daemon-reload >/dev/null 2>&1; then
        printf 'INFO     bus systemd utilisateur indisponible : service non activé\n'
        return
    fi
    if [ -x "$pericore_target" ]; then
        if ! systemctl --user enable pericored.service >/dev/null 2>&1 \
                || ! systemctl --user restart pericored.service >/dev/null 2>&1; then
            printf 'ATTENTION impossible d activer pericored.service ; consultez systemctl --user status pericored\n' >&2
        fi
    fi
}

write_launcher() {
    cat >"$launcher_target" <<EOF
#!/bin/sh
if [ "\$#" -gt 0 ]; then
    exec python3 "$cli_target" "\$@"
fi
exec python3 "$app_target" "\$@"
EOF
    chmod 0755 "$launcher_target"
}

ensure_local_bin_path() {
    local path_line='export PATH="$HOME/.local/bin:$PATH"'
    if [ -f "$shell_config" ] && grep -Fqx "$path_line" "$shell_config"; then
        return
    fi
    printf '\n# PeriphX V3\n%s\n' "$path_line" >>"$shell_config"
    : >"$path_marker"
    printf 'PATH Zsh ajouté dans %s\n' "$shell_config"
}

launch_v3() {
    if [ ! -x "$launcher_target" ]; then
        printf 'Application V3 absente. Lancez : %s install\n' "$0" >&2
        return 1
    fi
    exec "$launcher_target"
}

status_v3() {
    if [ -f "$state_file" ]; then
        printf 'OK       état V3 : %s\n' "$state_file"
        cat "$state_file"
    else
        printf 'ABSENT   état V3 : %s\n' "$state_file"
        return 1
    fi
}

restore_v3() {
    if ((dry_run)); then
        log_action "supprimer l'état V3 $state_dir"
        return
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user disable --now pericored.service >/dev/null 2>&1 || true
    fi
    if [ -f "$path_marker" ] && [ -f "$shell_config" ]; then
        sed -i '/^# PeriphX V3$/{N;/export PATH="\$HOME\/\.local\/bin:\$PATH"/d;}' "$shell_config"
    fi
    rm -f "$app_command" "$legacy_command" "$desktop_target" "$app_target" \
        "$cli_target" "$bin_dir/periphx-cli" "$launcher_target" "$pericore_command" \
        "$pericore_target" "$pericore_target.new" "$service_target"
    rm -rf "$state_dir"
    printf 'État V3 supprimé. Les fichiers V1 et V2 n ont pas été touchés.\n'
}

action="${1:-install}"
shift || true
if [ "${1:-}" = --dry-run ]; then
    dry_run=1
fi

case "$action" in
    check) check_v3 ;;
    install) install_v3 ;;
    dev) dev_v3 ;;
    launch) launch_v3 ;;
    status) status_v3 ;;
    restore) restore_v3 ;;
    help|-h|--help) usage ;;
    *) usage >&2; exit 2 ;;
esac
