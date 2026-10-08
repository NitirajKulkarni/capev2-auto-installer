#!/usr/bin/env bash
# CAPEv2 Automated Installer - Diagnostic Tool
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0 [--watch]"
    exit 1
fi

exec "${SCRIPT_DIR}/install.sh" --diagnose "$@"
