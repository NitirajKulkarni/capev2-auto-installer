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

# Robust Python interpreter detection
detect_python() {
    local candidate=""

    # 1. Check systemd services (primary source of truth: whatever systemd uses to run CAPE)
    for svc in /etc/systemd/system/cape.service /etc/systemd/system/cape-processor.service /etc/systemd/system/cape-web.service; do
        if [[ -f "$svc" ]]; then
            local svc_py
            svc_py=$(grep -oP '^ExecStart=\K\S+' "$svc" 2>/dev/null || true)
            if [[ -n "$svc_py" && -x "$svc_py" ]]; then
                if "$svc_py" -c "import sqlalchemy" &>/dev/null || sudo -u "$CAPE_USER" "$svc_py" -c "import sqlalchemy" &>/dev/null; then
                    echo "$svc_py"
                    return 0
                fi
            fi
        fi
    done

    # 2. Check virtual environment in CAPE_ROOT (.venv or venv)
    for candidate in \
        "${CAPE_ROOT}/.venv/bin/python3" \
        "${CAPE_ROOT}/.venv/bin/python" \
        "${CAPE_ROOT}/venv/bin/python3" \
        "${CAPE_ROOT}/venv/bin/python"; do
        if [[ -x "$candidate" ]]; then
            if "$candidate" -c "import sqlalchemy" &>/dev/null || sudo -u "$CAPE_USER" "$candidate" -c "import sqlalchemy" &>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    # 3. Check Poetry virtual environments
    for poetry_bin in "/etc/poetry/bin/poetry" "/home/${CAPE_USER}/.local/bin/poetry" "/usr/local/bin/poetry" "$(command -v poetry 2>/dev/null || true)"; do
        if [[ -n "$poetry_bin" && -x "$poetry_bin" ]]; then
            local poetry_env
            poetry_env=$(sudo -u "$CAPE_USER" "$poetry_bin" -C "$CAPE_ROOT" env info -p 2>/dev/null || true)
            if [[ -n "$poetry_env" && -x "${poetry_env}/bin/python" ]]; then
                if "${poetry_env}/bin/python" -c "import sqlalchemy" &>/dev/null || sudo -u "$CAPE_USER" "${poetry_env}/bin/python" -c "import sqlalchemy" &>/dev/null; then
                    echo "${poetry_env}/bin/python"
                    return 0
                fi
            fi
        fi
    done

    # Check cached virtualenvs in user directories
    for candidate in \
        /home/"${CAPE_USER}"/.cache/pypoetry/virtualenvs/*/bin/python \
        /root/.cache/pypoetry/virtualenvs/*/bin/python \
        /home/"${CAPE_USER}"/.local/share/virtualenvs/*/bin/python; do
        if [[ -x "$candidate" ]]; then
            if "$candidate" -c "import sqlalchemy" &>/dev/null || sudo -u "$CAPE_USER" "$candidate" -c "import sqlalchemy" &>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    # 4. Check system python3
    if command -v python3 &>/dev/null; then
        if python3 -c "import sqlalchemy" &>/dev/null || sudo -u "$CAPE_USER" python3 -c "import sqlalchemy" &>/dev/null; then
            echo "python3"
            return 0
        fi
    fi

    # 5. Fallback paths (if sqlalchemy check was inconclusive)
    for candidate in \
        "${CAPE_ROOT}/.venv/bin/python3" \
        "${CAPE_ROOT}/.venv/bin/python" \
        "${CAPE_ROOT}/venv/bin/python3" \
        "${CAPE_ROOT}/venv/bin/python"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done

    echo "python3"
}

PYTHON_BIN=$(detect_python)
CLEANER_SCRIPT="${CAPE_ROOT}/utils/cleaners.py"

if [[ ! -f "$CLEANER_SCRIPT" ]]; then
    echo "[-] Error: CAPEv2 cleaner script not found at ${CLEANER_SCRIPT}"
    exit 1
fi

run_cleaner() {
    cd "$CAPE_ROOT"
    sudo -u "$CAPE_USER" env PYTHONPATH="$CAPE_ROOT" "$PYTHON_BIN" "$CLEANER_SCRIPT" "$@"
}

show_help() {
    cat <<EOF
CAPEv2 Analysis Cleanup Helper
==============================
Usage: sudo $0 [OPTION]

Options:
  --all, -all         Completely delete ALL analysis tasks, stored binaries,
                      MongoDB records, and reset task counter to 1.
                      (Safely stops and restarts CAPE services during wipe)
                      Pass -y to bypass confirmation: sudo $0 --all -y

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

if [[ $# -eq 0 ]] || [[ "$1" =~ ^(-h|--help|help|-\?)$ ]]; then
    show_help
    exit 0
fi

echo "[*] Using Python: $PYTHON_BIN"

case "$1" in
    --all|-all|--clean|-clean|-a)
        echo "[*] WARNING: This will permanently delete ALL analysis tasks and reset database!"
        if [[ "${2:-}" =~ ^(-y|--yes|-f|--force)$ ]]; then
            confirm="y"
        else
            read -rp "Are you sure you want to proceed? [y/N]: " confirm
        fi
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo "[*] Aborted by user."
            exit 0
        fi

        echo "[*] Stopping CAPE services..."
        systemctl stop cape cape-processor cape-web || true

        echo "[*] Running CAPE full cleanup..."
        run_cleaner --clean

        echo "[*] Starting CAPE services..."
        systemctl start cape cape-processor cape-web || true
        echo "[+] Full cleanup complete. All previous analyses deleted."
        ;;

    --days|-days|-d)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --days requires a number of days (e.g. --days 7)"
            exit 1
        fi
        echo "[*] Deleting analysis tasks older than $2 days..."
        run_cleaner --days "$2"
        echo "[+] Done."
        ;;

    --failed|-failed|-f)
        echo "[*] Deleting all failed analysis tasks..."
        run_cleaner --failed
        echo "[+] Done."
        ;;

    --task|-task|--tasks|-tasks|--delete-tasks|-t)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --task requires task ID(s) (e.g. --task 11 or --task 11,14,15)"
            exit 1
        fi
        echo "[*] Deleting task(s): $2..."
        run_cleaner --delete-tasks "$2"
        echo "[+] Done."
        ;;

    --malscore|-malscore|-m)
        if [[ -z "${2:-}" ]]; then
            echo "[-] Error: --malscore requires a threshold (e.g. --malscore 2.0)"
            exit 1
        fi
        echo "[*] Deleting tasks with malscore <= $2..."
        run_cleaner --malscore "$2"
        echo "[+] Done."
        ;;

    --pcap|-pcap)
        echo "[*] Cleaning PCAP captures..."
        run_cleaner --pcap
        echo "[+] Done."
        ;;

    --bson|-bson)
        echo "[*] Cleaning MongoDB BSON dumps..."
        run_cleaner --bson
        echo "[+] Done."
        ;;

    --suricata|-suricata)
        echo "[*] Cleaning Suricata logs..."
        run_cleaner --suricata
        echo "[+] Done."
        ;;

    *)
        echo "[*] Forwarding options to CAPEv2 cleaner: $*"
        run_cleaner "$@"
        ;;
esac
