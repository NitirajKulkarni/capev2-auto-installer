#!/usr/bin/env bash
# CAPEv2 Automated Installer - Non-PE Support Enabler & Baseline Snapshot Tool (Alias)
# Usage: sudo ./enabled-nonpe.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0"
    exit 1
fi

exec "${SCRIPT_DIR}/enable-nonpe.sh" "$@"
