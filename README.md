<div align="center">

# 🦅 CAPEv2 Universal Automated Installer & Recovery Engine

**A dynamic, self-healing, universal installation and operational lifecycle engine for CAPEv2 Sandbox on Ubuntu hosts.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ubuntu: 24.04 | 22.04 LTS](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2022.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Target: CAPEv2](https://img.shields.io/badge/Sandbox-CAPEv2%20Latest-red.svg)](https://github.com/kevoreilly/CAPEv2)
[![Build: Push Ready](https://img.shields.io/badge/Git-Push%20Ready-success.svg)]()

**Author:** **Nitiraj Kulkarni**

</div>

---

## 📌 Executive Summary

Traditional CAPEv2 installation guides and community bash scripts assume a pristine, untouched Ubuntu installation, a single network topology, and immediate manual intervention upon any encountered error. In real-world enterprise environments, deployments encounter existing KVM setups, non-standard Python versions, running firewalls (UFW/nftables), existing databases, Docker/VPN interfaces, and transient network or package errors.

The **CAPEv2 Universal Automated Installer** solves this by replacing brittle shell sequences with a **deterministic 24-stage state machine**, an **autonomous environment discovery engine**, a **risk-tiered remediation framework**, and **strict resource ownership tracking**.

The core operational goal is:
```bash
sudo ./install.sh
```
yielding an end-to-end operational CAPEv2 sandbox with zero unnecessary drama.

---

## 🚀 Key Architectural Pillars

```
                     ┌────────────────────────────────────────┐
                     │    Stage 0: Environment Discovery      │
                     │  Ubuntu 24.04/22.04, KVM, CPU, Nets   │
                     └───────────────────┬────────────────────┘
                                         ▼
                     ┌────────────────────────────────────────┐
                     │     Stage 1: Preflight & Safety Checks │
                     │  SSH session check, AVX, disk, memory  │
                     └───────────────────┬────────────────────┘
                                         ▼
                     ┌────────────────────────────────────────┐
                     │    Stage 2-24: 24-Stage State Machine  │
                     │  Atomic Checkpoints & Resource Registry│
                     └───────┬────────────────────────┬───────┘
                             │                        │
                         [PASS]                     [FAIL]
                             │                        │
                             ▼                        ▼
                     ┌───────────────┐      ┌─────────────────┐
                     │ Next Stage /  │      │ Root-Cause Diag │
                     │ Success Report│      │  & Safe Repair  │
                     └───────────────┘      └────────┬────────┘
                                                     │
                                            [Verify & Resume]
```

### 1. Universal Environment Discovery
- **No Hardcoded Assumptions**: Dynamically discovers kernel, CPU virtualization (`vmx`/`svm`), network topology, default gateways, package manager state, and existing services.
- **Classification Engine**: Automatically classifies the host into `CAPE_RECOMMENDED` (Ubuntu 24.04 LTS), `CAPE_SUPPORTED` (Ubuntu 22.04 LTS), `CAPE_COMPATIBILITY_MODE`, or `UNSUPPORTED`.

### 2. Autonomous Diagnosis & Remediation Loop
- **Error Classification**: Process exits and stderr outputs are routed into typed categories (`PACKAGE_ERROR`, `SERVICE_ERROR`, `LIBVIRT_ERROR`, `PYTHON_ERROR`, `PERMISSION_ERROR`, `KVM_ERROR`, `DATABASE_ERROR`, `NETWORK_ERROR`).
- **Risk-Tiered Repairs**: Remediation actions follow strict safety policies (`LOW` = automatic, `MEDIUM` = configurable, `HIGH` = requires confirmation, `DESTRUCTIVE` = disabled by default).
- **Remote Session Protection**: Automatically detects SSH sessions (`SSH_CONNECTION`) and inhibits risky interface resets, preserving operator connectivity.

### 3. Strict Resource Ownership Registry
- **Zero Host Destruction**: The installer explicitly records every file, systemd unit, libvirt network, user account, and VM it creates. Existing host VMs, pre-installed databases, or network bridges are never removed or modified.

### 4. Zero Bootstrapping Dependencies
- Written in pure, standard Python (3.10+) with an embedded zero-dependency TOML parser fallback, ensuring execution on minimal Ubuntu cloud images without requiring pre-installed pip packages.

---

## ⚡ Quick Start

### 1. Clone & Enter Directory
```bash
git clone https://github.com/<your-org>/cape-auto-installer.git
cd cape-auto-installer
```

### 2. Inspect & Dry-Run (Preview Actions)
```bash
# Preview all 24 planned actions without modifying host state
sudo ./install.sh --dry-run

# Run non-destructive preflight capability audit
sudo ./install.sh --preflight
```

### 3. Run Full Installation
```bash
# Interactive mode
sudo ./install.sh

# Unattended / non-interactive (CI/CD / cloud-init)
sudo ./install.sh --non-interactive
```

---

## 🛠️ Operational CLI Commands

| Command | Action | Use Case |
|---------|--------|----------|
| `sudo ./install.sh` | **Full Install** | Runs discovery, installs dependencies, KVM, CAPE, and runs health tests. |
| `sudo ./install.sh --resume` | **Resume** | Safely picks up from the last checkpoint after reboot or intervention. |
| `sudo ./diagnose.sh` | **Diagnose** | Runs 11 subsystem probes across KVM, libvirt, network, and services. |
| `sudo ./diagnose.sh --watch` | **Monitor** | Real-time continuous health dashboard (auto-refreshing). |
| `sudo ./repair.sh` | **Self-Repair** | Automatically repairs broken services, package locks, and network interfaces. |
| `sudo ./status.sh` | **Status** | Displays status of all 24 stages and active checkpoints. |
| `sudo ./status.sh --drift` | **Drift Detection** | Detects drift between configuration and active runtime state. |
| `sudo ./uninstall.sh` | **Safe Uninstall** | Removes only resources created by this tool; leaves existing VMs safe. |
| `sudo ./uninstall.sh --full-reset` | **Full Wipe** | Complete cleanup including virtual disks and databases. |
| `sudo ./install.sh --self-test` | **Self-Test** | Validates framework command engine, state, and redaction internals. |

---

## 🔄 The 24-Stage Installation Pipeline

```
 [1] PREFLIGHT          Detect host capabilities, virtualization flags & RAM
 [2] BACKUP             Backup existing configurations to backups/
 [3] REPOSITORIES       Update APT sources, clean stale lists & configure mirrors
 [4] BASE_PACKAGES      Install essential build and network dependencies
 [5] KVM                Verify/install KVM, load kernel modules (kvm_intel/kvm_amd)
 [6] LIBVIRT            Configure libvirtd/virtqemud services and sockets
 [7] REBOOT_CHECK       Evaluate whether kernel update requires a reboot
 [8] CAPE_REPOSITORY    Clone or update KevReilly/CAPEv2 from GitHub
 [9] CAPE_DEPENDENCIES  Install system libraries (yara, tcpdump, libmagic)
[10] CAPE_INSTALL       Setup virtual environment and Python dependencies
[11] CAPE_CONFIG        Generate customized cuckoo.conf, kvm.conf, routing.conf
[12] DATABASE           Setup MongoDB / PostgreSQL backend
[13] SYSTEMD            Install systemd units (cape, cape-web, cape-processor, rooter)
[14] NETWORK            Create isolated analysis network and bridge (virbr-cape)
[15] VM_CREATE          Provision virtual disk and libvirt domain
[16] VM_INSTALL         Automate Windows guest unattended installation (if ISO given)
[17] VM_CONFIG          Harden guest baseline (disable defender, UAC, firewall)
[18] AGENT              Bootstrap CAPE Python/Go guest agent inside VM
[19] SNAPSHOT           Take clean analysis snapshot (cape-clean)
[20] MACHINERY_CONFIG   Bind VM snapshot parameters into CAPE kvm.conf
[21] CAPE_START         Start all CAPE systemd services in proper dependency order
[22] HEALTH_CHECK       Perform active HTTP, socket, and sniffer health checks
[23] END_TO_END_TEST    Execute synthetic task validation
[24] FINALIZE           Generate final Markdown and JSON status reports
```

---

## ⚙️ Configuration Reference (`config.toml`)

The installer is governed by `config.toml`. All parameters have secure defaults:

```toml
[installation]
cape_root = "/opt/CAPEv2"
cape_user = "cape"
cape_repo = "https://github.com/kevoreilly/CAPEv2.git"
cape_ref = "master"
python_manager = "auto"          # "auto", "poetry", "uv"
non_interactive = false
auto_repair = true
max_repair_attempts = 3

[safety]
allow_host_network_changes = false
allow_internet_routing = false
allow_firewall_changes = true
allow_reboot = false
preserve_existing_libvirt_vms = true
preserve_existing_networks = true
destructive_repair = false
remote_safe_mode = "auto"        # Auto-detects SSH connection

[network]
mode = "isolated"                # "isolated", "nat", "internet"
subnet = "192.168.250.0/24"
gateway = "192.168.250.1"
vm_ip_start = "192.168.250.100"
dns = "none"
libvirt_network_name = "cape-analysis"
cape_interface = "virbr1"
web_bind = "127.0.0.1"
web_port = 8000

[guest]
enabled = true
name = "cape-win"
platform = "windows"
iso_path = ""                    # Path to Windows ISO (if empty, VM setup is skipped)
disk_size_gb = 80
memory_mb = 8192
vcpus = 4
snapshot_name = "cape-clean"

[database]
backend = "auto"                 # "auto", "mongodb", "postgresql"
mongodb_host = "127.0.0.1"
mongodb_port = 27017
```

---

## 📁 Repository Directory Structure

```
cape-auto-installer/
├── .github/
│   └── workflows/
│       └── ci.yml                  # Multi-version CI workflow (Ubuntu 24.04/22.04)
├── docs/
│   ├── ARCHITECTURE.md             # In-depth architectural design specification
│   ├── CONFIGURATION.md            # Complete configuration variable reference
│   ├── RUNBOOK.md                  # Day-2 operator maintenance runbook
│   └── TROUBLESHOOTING.md          # Comprehensive issue and repair matrix
├── src/
│   └── cape_auto/
│       ├── __init__.py
│       ├── cli.py                  # CLI argument parsing and mode routing
│       ├── command.py              # Safe command execution engine with redaction
│       ├── config.py               # TOML config loader with stdlib fallback
│       ├── diagnostics.py          # 11 component diagnostic probes
│       ├── exceptions.py           # Structured exception hierarchy
│       ├── logging_setup.py        # Log rotation and secret filtering
│       ├── orchestrator.py         # 24-stage state machine orchestrator
│       ├── remediation.py          # Risk-tiered auto-remediation engine
│       ├── reporting.py            # Markdown & JSON report generator
│       └── state.py                # State persistence & resource ownership
├── templates/
│   ├── conf/                       # CAPE config templates (cuckoo, kvm, routing, web)
│   ├── libvirt/                    # Libvirt analysis network XML template
│   ├── systemd/                    # Systemd service templates (cape, web, rooter)
│   └── windows/                    # Unattended Windows answer file & setup scripts
├── tests/
│   ├── test_cli.py                 # CLI argument and flag tests
│   ├── test_command.py             # Command runner & timeout tests
│   ├── test_config.py              # Config parsing & validation tests
│   ├── test_diagnostics.py         # Diagnostic probe & reporting tests
│   ├── test_orchestrator.py        # Orchestration pipeline tests
│   ├── test_remediation.py         # Remediation classification tests
│   ├── test_reporting.py           # Report generation tests
│   └── test_state.py               # State machine & checkpointing tests
├── .gitattributes                  # Normalized line endings (LF for shell)
├── .gitignore                      # Clean repository ignore list
├── config.toml                     # Master configuration file
├── CONTRIBUTING.md                 # Contribution guidelines
├── diagnose.sh                     # Diagnostic entry point wrapper
├── install.sh                      # Master installer wrapper
├── LICENSE                         # GNU General Public License v3.0
├── README.md                       # Master documentation
├── repair.sh                       # Quick-repair wrapper
├── SECURITY.md                     # Security policy & isolation guarantees
├── status.sh                       # Status dashboard wrapper
└── uninstall.sh                    # Safe uninstaller wrapper
```

---

## 🧪 Testing & Verification

The framework includes a comprehensive test suite of **38 automated unit and integration tests** requiring zero external dependencies:

```bash
# Run unit test suite
python3 -m unittest discover tests -v

# Run internal framework self-test
python3 src/cape_auto/cli.py --self-test
```

All 38 test cases pass out-of-the-box across Python 3.10, 3.11, 3.12, and 3.13.

---

## 👤 Author & Maintainer

**Nitiraj V. Kulkarni**  


---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see the [LICENSE](LICENSE) file for complete details. Compatible with the official [CAPEv2 Sandbox](https://github.com/kevoreilly/CAPEv2) ecosystem.
