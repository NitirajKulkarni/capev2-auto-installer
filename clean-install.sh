#!/usr/bin/env bash
# CAPEv2 Automated Installer - Clean Installation Entry Point
# Wipes previous CAPE installation, services, VM, and state, then performs fresh install.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"
if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0 [OPTIONS]"
    exit 1
fi
exec "${SCRIPT_DIR}/install.sh" --clean-install "$@"
