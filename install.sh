#!/usr/bin/env bash
# CAPEv2 Automated Installer - Entry Point
# Copyright (c) 2026. See LICENSE for details.
#
# Usage: sudo ./install.sh [OPTIONS]
# See:   sudo ./install.sh --help
set -euo pipefail

# ─── Constants ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/run/lock/cape-auto-installer.lock"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
LOG_DIR="${SCRIPT_DIR}/logs"
STATE_DIR="${SCRIPT_DIR}/state"

# ─── Color helpers ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# ─── Help ────────────────────────────────────────────────────────────────────
show_help() {
    cat <<'HELP'
CAPEv2 Automated Installer
===========================

Usage:
    sudo ./install.sh                   Full installation (interactive)
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
    sudo ./install.sh --help            Show this help

Configuration:
    Edit config.toml before running, or accept safe defaults.
    Supply Windows ISO path in config.toml for guest automation.

Examples:
    # Fresh install with defaults
    sudo ./install.sh

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
        echo "  Usage: sudo $0 $*"
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
    echo $$ > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# ─── Signal handling ─────────────────────────────────────────────────────────
cleanup() {
    local exit_code=$?
    log_warn "Installer interrupted (signal received)."
    log_info "State has been saved. Resume with: sudo ./install.sh --resume"
    release_lock
    exit $exit_code
}
trap cleanup SIGINT SIGTERM SIGHUP

# ─── Python discovery ───────────────────────────────────────────────────────
find_python() {
    local candidates=(
        python3.12
        python3.11
        python3.10
        python3
    )
    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            if [[ -n "$ver" ]]; then
                local major minor
                major=$(echo "$ver" | cut -d. -f1)
                minor=$(echo "$ver" | cut -d. -f2)
                if [[ $major -ge $MIN_PYTHON_MAJOR && $minor -ge $MIN_PYTHON_MINOR ]]; then
                    PYTHON_BIN=$(command -v "$cmd")
                    log_ok "Found Python $ver at $PYTHON_BIN"
                    return 0
                fi
            fi
        fi
    done
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
    local log_file="${LOG_DIR}/run-$(date '+%Y%m%d-%H%M%S').log"
    exec > >(tee -a "$log_file") 2>&1

    log_info "CAPEv2 Automated Installer starting..."
    log_info "Log file: $log_file"
    log_info "Working directory: $SCRIPT_DIR"

    ensure_python

    # Delegate to Python orchestrator
    log_info "Launching Python orchestrator..."
    local exit_code=0
    "$PYTHON_BIN" -u "${SCRIPT_DIR}/src/cape_auto/cli.py" "$@" || exit_code=$?

    release_lock

    if [[ $exit_code -eq 0 ]]; then
        log_ok "Installer completed successfully."
    elif [[ $exit_code -eq 42 ]]; then
        log_info "Reboot required. After reboot, run: sudo ./install.sh --resume"
    elif [[ $exit_code -eq 43 ]]; then
        log_warn "Manual intervention required. See reports/ directory."
    else
        log_error "Installer failed with exit code $exit_code"
        log_info "Run 'sudo ./install.sh --diagnose' for troubleshooting."
        log_info "Run 'sudo ./install.sh --resume' to retry from last checkpoint."
    fi
    exit $exit_code
}

main "$@"
