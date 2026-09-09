#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-menu}" in
    report|hardware-report) python3 "$repo_dir/core/hardware.py" --json ;;
    test) PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$repo_dir/tests" ;;
    menu)
        cat <<'EOF'
Mode contribution Deblestia
  ./contribute.sh report  Rapport matériel anonymisé, affiché localement
  ./contribute.sh test    Validation du socle installateur

Aucune donnée n’est envoyée automatiquement.
EOF
        ;;
    *) printf 'Usage : %s [menu|report|test]\n' "$0" >&2; exit 2 ;;
esac
