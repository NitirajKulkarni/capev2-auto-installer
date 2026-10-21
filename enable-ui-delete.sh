#!/usr/bin/env bash
# ==============================================================================
# CAPEv2 Auto-Installer Helper: Enable / Disable Delete Button in Web UI
# ==============================================================================
# Usage:
#   sudo ./enable-ui-delete.sh            # Enables delete button in Web UI
#   sudo ./enable-ui-delete.sh --disable  # Disables delete button in Web UI
#   sudo ./enable-ui-delete.sh --status   # Checks current status
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Usage: sudo $0 [--disable|--status]"
    exit 1
fi

case "${1:-}" in
    --disable|-disable|-d)
        exec "${SCRIPT_DIR}/clean-analyses.sh" --disable-ui-delete
        ;;
    --status|-status|-s)
        exec "${SCRIPT_DIR}/clean-analyses.sh" --ui-delete-status
        ;;
    --help|-h|help)
        cat <<EOF
Usage: sudo $0 [OPTION]

Options:
  (no args)    Enable task deletion button in CAPEv2 Web UI and restart cape-web.
  --disable    Disable task deletion button in CAPEv2 Web UI.
  --status     Check whether task deletion is currently enabled.
  -h, --help   Show this help message.
EOF
        exit 0
        ;;
    *)
        exec "${SCRIPT_DIR}/clean-analyses.sh" --enable-ui-delete
        ;;
esac
