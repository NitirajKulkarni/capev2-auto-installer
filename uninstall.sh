#!/usr/bin/env bash
# CAPEv2 Automated Installer - Uninstaller
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"
if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0 [--keep-cape-user] [--keep-data] [--keep-vm] [--full-reset]"
    exit 1
fi
exec "${SCRIPT_DIR}/install.sh" --uninstall "$@"
