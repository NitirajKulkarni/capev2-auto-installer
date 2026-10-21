#!/usr/bin/env bash
# ==============================================================================
# CAPEv2 Auto-Installer Helper: Delete & Clean Old Analysis Tasks
# ==============================================================================
# Usage:
#   sudo ./clean-analyses.sh --all            # Wipes ALL analysis tasks & resets ID to 1
#   sudo ./clean-analyses.sh --days 7         # Deletes analyses older than 7 days
#   sudo ./clean-analyses.sh --failed         # Deletes only failed / error tasks
#   sudo ./clean-analyses.sh --task 11,14,15  # Deletes specific task IDs
#   sudo ./clean-analyses.sh --malscore 2.0   # Deletes benign/low-risk samples (score <= 2.0)
#   sudo ./clean-analyses.sh --pcap           # Deletes PCAP network captures to free space
# ==============================================================================

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[!] Error: This script must be run as root (use sudo)."
    exit 1
fi

CAPE_ROOT="/opt/CAPEv2"
CAPE_USER="cape"

# Detect Python interpreter
if [[ -f "${CAPE_ROOT}/venv/bin/python3" ]]; then
    PYTHON_BIN="${CAPE_ROOT}/venv/bin/python3"
elif [[ -f "${CAPE_ROOT}/poetry.lock" ]] && command -v poetry &>/dev/null; then
    PYTHON_BIN="poetry run python"
else
    PYTHON_BIN="python3"
fi

CLEANER_SCRIPT="${CAPE_ROOT}/utils/cleaners.py"

if [[ ! -f "$CLEANER_SCRIPT" ]]; then
    echo "[-] Error: CAPEv2 cleaner script not found at ${CLEANER_SCRIPT}"
    exit 1
fi

show_help() {
    cat <<EOF
CAPEv2 Analysis Cleanup Helper
==============================
Usage: sudo $0 [OPTION]

Options:
  --all               Completely delete ALL analysis tasks, stored binaries,
                      MongoDB records, and reset task counter to 1.
                      (Safely stops and restarts CAPE services during wipe)

  --days <N>          Delete all analysis tasks older than <N> days.
                      Example: sudo $0 --days 14

  --failed            Delete all failed, aborted, or error analysis tasks.

  --task <ID,ID,...>  Delete specific task IDs.
                      Example: sudo $0 --task 11,14,15

  --malscore <SCORE>  Delete benign samples with threat score <= <SCORE>.
                      Example: sudo $0 --malscore 2.0

  --pcap              Delete raw PCAP network captures to recover disk space.

  --bson              Delete raw MongoDB BSON dumps.

  --suricata          Delete Suricata alert log files.

  -h, --help          Show this help message.
EOF
}

if [[ $# -eq 0 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_help
    exit 0
fi

case "$1" in
    --all)
        echo "[*] WARNING: This will permanently delete ALL analysis tasks and reset database!"
        read -rp "Are you sure you want to proceed? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo "[*] Aborted by user."
            exit 0
        fi

        echo "[*] Stopping CAPE services..."
        systemctl stop cape cape-processor cape-web || true

        echo "[*] Running CAPE full cleanup..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --clean

        echo "[*] Starting CAPE services..."
        systemctl start cape cape-processor cape-web || true
        echo "[+] Full cleanup complete. All previous analyses deleted."
        ;;

    --days)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --days requires a number of days (e.g. --days 7)"
            exit 1
        fi
        echo "[*] Deleting analysis tasks older than $2 days..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --days "$2"
        echo "[+] Done."
        ;;

    --failed)
        echo "[*] Deleting all failed analysis tasks..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --failed
        echo "[+] Done."
        ;;

    --task)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --task requires task ID(s) (e.g. --task 11 or --task 11,14,15)"
            exit 1
        fi
        echo "[*] Deleting task(s): $2..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --delete-tasks "$2"
        echo "[+] Done."
        ;;

    --malscore)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --malscore requires a threshold (e.g. --malscore 2.0)"
            exit 1
        fi
        echo "[*] Deleting tasks with malscore <= $2..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --malscore "$2"
        echo "[+] Done."
        ;;

    --pcap)
        echo "[*] Cleaning PCAP captures..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --pcap
        echo "[+] Done."
        ;;

    --bson)
        echo "[*] Cleaning MongoDB BSON dumps..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --bson
        echo "[+] Done."
        ;;

    --suricata)
        echo "[*] Cleaning Suricata logs..."
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" --suricata
        echo "[+] Done."
        ;;

    *)
        echo "[*] Forwarding options to CAPEv2 cleaner: $*"
        sudo -u "$CAPE_USER" $PYTHON_BIN "$CLEANER_SCRIPT" "$@"
        ;;
esac
