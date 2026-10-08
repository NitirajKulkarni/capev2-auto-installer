<div align="center">

# 🦅 CAPEv2 Universal Automated Installer & Recovery Engine

**A dynamic, self-healing, universal installation and operational lifecycle engine for CAPEv2 Sandbox on Ubuntu hosts.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ubuntu: 24.04 | 22.04 LTS](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2022.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/NitirajKulkarni/capev2-auto-installer/actions/workflows/ci.yml/badge.svg)](https://github.com/NitirajKulkarni/capev2-auto-installer/actions/workflows/ci.yml)

**Author & Maintainer:** [**Nitiraj Kulkarni**](https://github.com/NitirajKulkarni)

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

## 🖥️ Supported Host Environments

The installer is engineered to automatically detect and adapt to both **physical bare-metal servers** and **virtual machine hosts**.

### 1. Operating System Compatibility
| Platform | Version | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Ubuntu 24.04 LTS** (*Noble Numbat*) | 24.04.x | **Recommended / Primary** | Kernel 6.8+, native Netplan & systemd v255, Python 3.12 default. |
| **Ubuntu 22.04 LTS** (*Jammy Jellyfish*) | 22.04.x | **Fully Supported** | Kernel 5.15+, Python 3.10 default (native bootstrap fallback). |

### 2. Bare Metal vs. Virtual Machine (Nested Virtualization)
- **Bare-Metal Physical Host**:
  Hardware virtualization (`vmx` on Intel, `svm` on AMD) must be enabled in the BIOS/UEFI.
- **Ubuntu Host inside a Virtual Machine (Nested Virtualization)**:
  Because CAPEv2 provisions analysis VMs using KVM inside your Ubuntu host, the parent hypervisor must expose hardware virtualization to the Ubuntu VM.

#### Hypervisor Configuration Guide for Nested Virtualization
| Hypervisor | Configuration Steps |
| :--- | :--- |
| **VMware Workstation / Player / Fusion** | Power off VM &rarr; *Virtual Machine Settings* &rarr; *Processors* &rarr; Check **"Virtualize Intel VT-x/EPT or AMD-V/RVI"**. |
| **Oracle VirtualBox** | Power off VM &rarr; *Settings* &rarr; *System* &rarr; *Processor* &rarr; Check **"Enable Nested VT-x/AMD-V"**. |
| **Proxmox VE** | Select VM &rarr; *Hardware* &rarr; *Processors* &rarr; Set CPU Type to **`host`**. |
| **Microsoft Hyper-V** | In Administrator PowerShell on Windows: <br>`Set-VMProcessor -VMName "<Your-Ubuntu-VM>" -ExposeVirtualizationExtensions $true` |
| **KVM / QEMU (Parent Host)** | Start VM with `-cpu host` or configure `<cpu mode='host-passthrough'/>` in libvirt XML. |
| **Cloud Instances (AWS / Azure / GCP)** | Must use instances with nested virtualization enabled (e.g. AWS `*.metal`, Azure `Dv3`/`Dv4`/`Dv5` series). |

> [!IMPORTANT]
> **Windows 10/11 Host Automated Fix (VirtualBox / VMware):**  
> If you enabled "Nested VT-x/AMD-V" in VirtualBox or VMware and Ubuntu *still* reports `[FAIL] No hardware virtualization support`, Windows Virtualization-Based Security (VBS) or Hyper-V is running in the background and locking the CPU in "NEM / Snail Mode".  
> **1-Click Automated Fix:** Run the included [`enable-windows-virtualization.bat`](enable-windows-virtualization.bat) on your Windows machine as Administrator, select **`[1]`**, and reboot Windows.

---

## ⚡ Quick Start & Verification Workflow

### Step 1: Clone Repository & Ensure Permissions
```bash
git clone https://github.com/NitirajKulkarni/capev2-auto-installer.git
cd capev2-auto-installer

# Ensure all wrapper scripts have execution permissions
chmod +x *.sh
```

### Step 2: Validate Environment (Zero Risk / Non-Destructive)
Before installing, run the non-destructive verification sequence to audit your host:
```bash
# 1. Verify internal framework engines (command runner, redaction, state)
sudo ./install.sh --self-test

# 2. Audit hardware virtualization, RAM, disk space, and network topology
sudo ./install.sh --preflight

# 3. Simulate all 24 installation stages without applying any changes
sudo ./install.sh --dry-run
```

### Step 3: Run Full Installation
```bash
# Standard interactive mode (recommended for first-time setup)
sudo ./install.sh

# Unattended / non-interactive (ideal for automated CI/CD and cloud-init)
sudo ./install.sh --non-interactive
```

### Step 4: Resume Interrupted Installations
If a reboot is required or a stage pauses for manual intervention, resume seamlessly from the last atomic checkpoint:
```bash
sudo ./install.sh --resume
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
windows_edition = "win10_eval"    # "win10_eval" (recommended) or "win11_eval"
auto_download_iso = false         # Set to true or use --auto-download-iso
iso_path = ""                     # Path to Windows ISO (if already downloaded)
eval_iso_url = ""                 # Optional custom mirror URL
disk_size_gb = 80
memory_mb = 8192
vcpus = 4
snapshot_name = "cape-clean"
uefi = ""                         # Auto-detected based on edition

[database]
backend = "auto"                 # "auto", "mongodb", "postgresql"
mongodb_host = "127.0.0.1"
mongodb_port = 27017
```

---

## 🪟 Windows Guest Provisioning & Analysis OS Policy

CAPEv2 dynamic malware analysis requires **full-fidelity, untampered Windows operating systems** to capture authentic behavioral traces, API hooks, and network telemetry.

### 🛡️ Strictly Prohibited: Tiny11 & Stripped Windows Builds
> [!CAUTION]
> **Strictly NO Tiny11, Tiny10, or stripped custom ISOs!**  
> Stripped OS builds (such as Tiny11, Micro10, GhostSpectre, or ReviOS) remove vital operating system subsystems:
> - **Windows Defender & AMSI (Antimalware Scan Interface)**: Stripped out. Malware checks for Defender presence to deploy bypasses or detect sandboxes.
> - **Event Tracing for Windows (ETW)**: Kernel trace providers disabled, blinding behavioral analyzers.
> - **WMI Providers & Namespaces**: Malware queries WMI for evasion; on stripped builds, queries crash the sample.
> - **Task Scheduler & BITS**: Persistence mechanisms fail to execute.
> - **Authentic Registry Hives & COM Objects**: Real-world malware terminates or refuses to detonate when missing.
> 
> The installer enforces this policy at configuration time and during ISO verification.

### 🌟 Supported: Official Microsoft Enterprise Evaluation ISOs
The installer provides full automated support for official Microsoft 90-day Evaluation ISOs:
| Edition | Config Value | Minimum Disk | Recommended RAM | Firmware | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Windows 10 Enterprise Eval** | `win10_eval` | 60 GB | 4096 - 8192 MB | BIOS / SeaBIOS | **Recommended for speed, stability, and broad malware compatibility.** |
| **Windows 11 Enterprise Eval** | `win11_eval` | 80 GB | 8192 MB+ | UEFI + TPM 2.0 | Automated with OVMF UEFI and TPM emulator (`swtpm`). |

#### One-Click Auto-Download:
```bash
# Auto-download Windows 10 Enterprise Evaluation ISO & provision VM:
sudo ./install.sh --auto-download-iso

# Auto-download Windows 11 Enterprise Evaluation ISO:
sudo ./install.sh --windows-edition win11_eval --auto-download-iso
```

---

## 📊 Live Progress Bar & Clean Terminal UI

The installer features an organized, real-time ASCII progress bar and stage dashboard:
- **ASCII Progress Bar**: Displays stage completion percentage:
  ```
  ══════════════════════════════════════════════════════════════════════════════
    [██████████████████░░░░░░░░]  62%  |  STAGE 15/24: VM_CREATE
    ▶ Task:        Create analysis VM (Windows 10 Enterprise Evaluation)
    ▶ Attempt:     1 of 3   |   Started: 2026-10-08 13:30:00 UTC
  ══════════════════════════════════════════════════════════════════════════════
  ```
- **Real-Time Streaming (`live_output`)**: Commands like `uv sync` and APT operations stream live progress without silent terminal freezing.
- **Resumable ISO Downloader**: Downloads Microsoft Evaluation ISOs with chunked streaming and dynamic MB/s + ETA tracking:
  ```
  [ISO DL] [████████████████░░░░░░░░]  68.4% (3.42/5.00 GB) | 24.1 MB/s | ETA: 01:05
  ```
- **Python 3.12 Pinning**: Automatically isolates CAPEv2 into a Python 3.12 environment via `uv`/`poetry`, completely eliminating `python-flirt` wheel missing errors on Python 3.14 hosts and ensuring `django` and `cape-web.service` run stably.

---

## 📁 Repository Directory Structure

```
capev2-auto-installer/
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

## 🩺 Troubleshooting & Diagnostics Runbook

If you encounter an issue during installation or daily operation, consult the matrix below:

| Symptom / Error Message | Root Cause | Solution |
| :--- | :--- | :--- |
| `Permission denied (os error 13)` | Shell scripts missing executable bit (`+x`). | Run `chmod +x *.sh` or run with `sudo bash ./install.sh`. |
| `No hardware virtualization support (VT-x/AMD-V)` | Virtualization disabled in BIOS or nested virt off in hypervisor. | Enable Intel VT-x or AMD-V in BIOS/UEFI. If inside a VM, enable Nested Virtualization in hypervisor settings (e.g. VMware "Virtualize Intel VT-x", Proxmox CPU `host`, VirtualBox "Enable Nested VT-x"). |
| `/dev/kvm not found` | KVM kernel module not loaded. | Run `sudo modprobe kvm_intel` or `sudo modprobe kvm_amd`. The installer attempts auto-loading. |
| `Another installer instance is running (PID: ...)` | Previous installation interrupted; stale lock file remains. | Resume with `sudo ./install.sh --resume`, or remove `/run/lock/cape-auto-installer.lock` if process is dead. |
| `Reboot required (Exit Code 42)` | New kernel or hypervisor modules installed requiring system reload. | Reboot with `sudo reboot`, then resume with `sudo ./install.sh --resume`. |
| `Manual intervention required (Exit Code 43)` | Unresolvable conflict (e.g., port occupied, disk full, missing ISO). | Review the generated Markdown report at `reports/manual-intervention.md`, apply recommended fix, and resume. |
| `Package lock held / Could not get lock /var/lib/dpkg/lock` | Background package manager active (`unattended-upgrades`). | The installer retries automatically. Alternatively, wait 60s or run `sudo ./repair.sh`. |
| Broken service or failed dependency | Systemd unit or network interface drifted. | Run `sudo ./repair.sh` to trigger self-healing, or `sudo ./diagnose.sh` to isolate failing component. |

### Diagnostic Dashboards
```bash
# Run one-shot 11-subsystem diagnostic audit
sudo ./diagnose.sh

# Continuous real-time health monitoring
sudo ./diagnose.sh --watch

# Check stage progression and drift
sudo ./status.sh
sudo ./status.sh --drift
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

**Nitiraj Kulkarni** ([@NitirajKulkarni](https://github.com/NitirajKulkarni))


---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see the [LICENSE](LICENSE) file for complete details. Compatible with the official [CAPEv2 Sandbox](https://github.com/kevoreilly/CAPEv2) ecosystem.
