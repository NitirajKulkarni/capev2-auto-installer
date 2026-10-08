#!/usr/bin/env bash
# CAPEv2 Automated Installer - Status Dashboard
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"
if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0 [--drift]"
    exit 1
fi
exec "${SCRIPT_DIR}/install.sh" --status "$@"
