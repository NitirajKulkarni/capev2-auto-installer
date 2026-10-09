#!/usr/bin/env bash
# CAPEv2 Automated Installer - Entry Point
# Copyright (c) 2026. See LICENSE for details.
#
# Usage: sudo ./install.sh [OPTIONS]
# See:   sudo ./install.sh --help
set -euo pipefail

# ─── Constants ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1; pwd)"
LOCK_FILE="/run/lock/cape-auto-installer.lock"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
LOG_DIR="${SCRIPT_DIR}/logs"
STATE_DIR="${SCRIPT_DIR}/state"
PYTHON_BIN=""

# ─── Color helpers ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { printf "%b[INFO]%b  %s %s\n" "${CYAN}" "${NC}" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
log_ok()    { printf "%b[OK]%b    %s %s\n" "${GREEN}" "${NC}" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
log_warn()  { printf "%b[WARN]%b  %s %s\n" "${YELLOW}" "${NC}" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
log_error() { printf "%b[ERROR]%b %s %s\n" "${RED}" "${NC}" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# ─── Help ────────────────────────────────────────────────────────────────────
show_help() {
    cat <<'HELP'
CAPEv2 Automated Installer
===========================

Usage:
    sudo ./install.sh                   Full installation (interactive)
    sudo ./install.sh --clean-install   Clean install: wipe previous installation & install from scratch
    sudo ./install.sh --non-interactive Non-interactive mode
    sudo ./install.sh --resume          Resume interrupted installation
    sudo ./install.sh --repair          Repair broken installation
    sudo ./install.sh --diagnose        Run diagnostic checks only
    sudo ./install.sh --status          Show installation status
    sudo ./install.sh --dry-run         Show what would be done
    sudo ./install.sh --preflight       Run preflight checks only
    sudo ./install.sh --from-stage <s>  Resume from specific stage
    sudo ./install.sh --reset-failed    Reset failed stage and retry
    sudo ./install.sh --update          Update existing CAPEv2
    sudo ./install.sh --self-test       Run framework self-tests
    sudo ./install.sh --auto-download-iso Auto-download official Windows Eval ISO
    sudo ./install.sh --windows-edition <ed> Windows edition: win10_eval (default) or win11_eval
    sudo ./install.sh --help            Show this help

Configuration:
    Edit config.toml before running, or accept safe defaults.
    Windows 10/11 Enterprise Evaluation ISOs supported for malware analysis.
    (Strictly NO Tiny11 - stripped builds break telemetry and analysis).

Examples:
    # Fresh install with defaults (Windows 10 Enterprise Eval)
    sudo ./install.sh

    # Complete clean reinstall (wipes prior VMs, disks, /opt/CAPEv2, and state)
    sudo ./install.sh --clean-install
    # or using the shortcut wrapper:
    sudo ./clean-install.sh

    # Auto-download Windows 10 Enterprise Eval ISO
    sudo ./install.sh --auto-download-iso

    # Auto-download Windows 11 Enterprise Eval ISO
    sudo ./install.sh --windows-edition win11_eval --auto-download-iso

    # Resume after reboot
    sudo ./install.sh --resume

    # Diagnose issues
    sudo ./install.sh --diagnose

    # Repair without reinstalling
    sudo ./install.sh --repair

    # Check status dashboard
    sudo ./install.sh --status

Environment Variables:
    CAPE_CONFIG     Path to config.toml (default: ./config.toml)
    CAPE_LOG_LEVEL  Log level: DEBUG, INFO, WARN, ERROR (default: INFO)
    CAPE_NO_COLOR   Disable colored output if set to 1
HELP
}

# ─── Privilege check ─────────────────────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This installer must be run as root."
        printf "  Usage: sudo %s %s\n" "$0" "$*"
        exit 1
    fi
}

# ─── OS detection ────────────────────────────────────────────────────────────
check_os() {
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect operating system. /etc/os-release not found."
        exit 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        log_error "This installer supports Ubuntu only. Detected: ${ID:-unknown}"
        exit 1
    fi
    log_info "Detected: ${PRETTY_NAME:-Ubuntu}"
}

# ─── Lock management ────────────────────────────────────────────────────────
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local lock_pid
        lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
        if [[ "$lock_pid" != "unknown" ]] && kill -0 "$lock_pid" 2>/dev/null; then
            log_error "Another installer instance is running (PID: $lock_pid)."
            log_error "If this is wrong, remove $LOCK_FILE"
            exit 1
        else
            log_warn "Stale lock file found. Removing."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo "$$" > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# ─── Signal handling ─────────────────────────────────────────────────────────
# shellcheck disable=SC2317
cleanup() {
    local exit_code
    exit_code=$?
    log_warn "Installer interrupted (signal received)."
    log_info "State has been saved. Resume with: sudo ./install.sh --resume"
    release_lock
    exit "$exit_code"
}
trap cleanup SIGINT SIGTERM SIGHUP

# ─── Python discovery ───────────────────────────────────────────────────────
find_python() {
    local cmd ver major minor
    local candidates=(
        python3.12
        python3.11
        python3.10
    )
    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            if [[ -n "$ver" ]]; then
                major="${ver%%.*}"
                minor="${ver##*.}"
                if [[ $major -eq $MIN_PYTHON_MAJOR && $minor -ge $MIN_PYTHON_MINOR && $minor -le 12 ]]; then
                    PYTHON_BIN=$(command -v "$cmd")
                    log_ok "Found compatible Python $ver at $PYTHON_BIN (pinned for CAPEv2 dependencies)"
                    return 0
                fi
            fi
        fi
    done

    # Fallback to system python3, warning if > 3.12 (e.g. Python 3.14)
    if command -v python3 &>/dev/null; then
        ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        if [[ -n "$ver" ]]; then
            major="${ver%%.*}"
            minor="${ver##*.}"
            if [[ $major -ge $MIN_PYTHON_MAJOR && $minor -ge $MIN_PYTHON_MINOR ]]; then
                if [[ $minor -gt 12 ]]; then
                    log_warn "Host Python is $ver (> 3.12). CAPEv2 wheels (python-flirt) require Python 3.12."
                    log_info "Attempting to install python3.12 package..."
                    if command -v apt-get &>/dev/null; then
                        apt-get update -qq 2>/dev/null || true
                        apt-get install -y python3.12 python3.12-venv python3.12-dev 2>/dev/null || true
                        if command -v python3.12 &>/dev/null; then
                            PYTHON_BIN=$(command -v python3.12)
                            log_ok "Installed and selected Python 3.12 at $PYTHON_BIN"
                            return 0
                        fi
                    fi
                fi
                PYTHON_BIN=$(command -v python3)
                log_ok "Using Python $ver at $PYTHON_BIN (uv will manage isolated Python 3.12 environment)"
                if ! command -v uv &>/dev/null && [[ ! -f /usr/local/bin/uv ]]; then
                    log_info "Ensuring uv is installed to /usr/local/bin for isolated Python 3.12 management..."
                    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh 2>/dev/null || true
                fi
                return 0
            fi
        fi
    fi
    return 1
}

ensure_python() {
    if find_python; then
        return 0
    fi
    log_warn "No suitable Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} found."
    log_info "Attempting to install python3..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq 2>/dev/null || true
        # Try python3.12 first, then fallback
        if apt-get install -y python3.12 2>/dev/null; then
            find_python && return 0
        fi
        if apt-get install -y python3.11 2>/dev/null; then
            find_python && return 0
        fi
        if apt-get install -y python3 2>/dev/null; then
            find_python && return 0
        fi
    fi
    log_error "Cannot find or install Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}"
    log_error "Please install Python 3.10+ manually and re-run this installer."
    exit 1
}

# ─── Directory setup ─────────────────────────────────────────────────────────
setup_directories() {
    mkdir -p "$LOG_DIR" "$STATE_DIR" "${SCRIPT_DIR}/backups" "${SCRIPT_DIR}/reports"
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
    # Handle --help before root check
    for arg in "$@"; do
        if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
            show_help
            exit 0
        fi
    done

    check_root "$@"
    check_os
    setup_directories
    acquire_lock

    # Log everything
    local log_file
    log_file="${LOG_DIR}/run-$(date '+%Y%m%d-%H%M%S').log"
    exec > >(tee -a "$log_file") 2>&1

    log_info "CAPEv2 Automated Installer starting..."
    log_info "Log file: $log_file"
    log_info "Working directory: $SCRIPT_DIR"

    ensure_python

    # Optimize network stack: prioritize IPv4 to eliminate 10s IPv6 connect timeouts on VM NAT
    if [[ -f /etc/gai.conf ]]; then
        if ! grep -qE '^precedence\s+::ffff:0:0/96\s+100' /etc/gai.conf 2>/dev/null; then
            sed -i 's/^#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/' /etc/gai.conf 2>/dev/null || true
            if ! grep -qE '^precedence\s+::ffff:0:0/96\s+100' /etc/gai.conf 2>/dev/null; then
                echo "precedence ::ffff:0:0/96  100" >> /etc/gai.conf 2>/dev/null || true
            fi
            log_info "Configured /etc/gai.conf to prioritize IPv4 (eliminating IPv6 NAT connect timeouts)."
        fi
    fi

    # Optimize network interface offloading: disable TSO/GSO to prevent 50KB/s throttling over VM NAT
    ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v 'lo' | while IFS= read -r iface; do
        if [ -n "$iface" ]; then
            ethtool -K "$iface" tso off gso off gro off 2>/dev/null || true
        fi
    done || true

    # Optimize uv network parameters: higher concurrency (16) for speed, protected by TSO/GSO offload disable
    export UV_HTTP_TIMEOUT=120
    export UV_HTTP_CONNECT_TIMEOUT=15
    export UV_HTTP_RETRIES=5
    export UV_CONCURRENT_DOWNLOADS=16

    # Delegate to Python orchestrator
    log_info "Launching Python orchestrator..."
    local exit_code=0
    "$PYTHON_BIN" -u "${SCRIPT_DIR}/src/cape_auto/cli.py" "$@" || exit_code=$?

    release_lock

    if [[ $exit_code -eq 0 ]]; then
        log_ok "Installer completed successfully."
        if [[ -x /usr/local/bin/cape-launch ]]; then
            log_ok "CAPEv2 Home Screen shortcut ready! Double-click 'CAPEv2 Sandbox' on your Desktop to start."
            log_ok "Web interface: http://127.0.0.1:8000"
        fi
    elif [[ $exit_code -eq 42 ]]; then
        log_info "Reboot required. After reboot, run: sudo ./install.sh --resume"
    elif [[ $exit_code -eq 43 ]]; then
        log_warn "Manual intervention required. See reports/ directory."
    else
        log_error "Installer failed with exit code $exit_code"
        log_info "Run 'sudo ./install.sh --diagnose' for troubleshooting."
        log_info "Run 'sudo ./install.sh --resume' to retry from last checkpoint."
    fi
    exit "$exit_code"
}

main "$@"
