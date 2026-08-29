#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
action="${1:-install}"
exec "$repo_dir/install.sh" "$action" nova
