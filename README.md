<div align="center">

# 🦅 CAPEv2 Universal Automated Installer & Sandbox Orchestrator

**A self-healing, zero-touch, automated installation and lifecycle engine for CAPEv2 Sandbox on Ubuntu hosts.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ubuntu: 24.04 | 22.04 LTS](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2022.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Guest: Answer Disc Provisioning](https://img.shields.io/badge/Windows-Answer%20Disc%20Provisioning-0078D6?logo=windows&logoColor=white)](templates/windows/)
[![CI: Automated Test Suite](https://img.shields.io/badge/CI-Passing%20(60%20Tests)-brightgreen.svg)](tests/)

<br />

**Author & Maintainer:** [**Nitiraj V. Kulkarni — AI Safety & Cybersecurity Researcher**](https://nitirajkulkarni.in/)  
[![Website](https://img.shields.io/badge/Website-nitirajkulkarni.in-0078D6?style=flat&logo=googlechrome&logoColor=white)](https://nitirajkulkarni.in/)
[![Google Scholar](https://img.shields.io/badge/Google_Scholar-Citations-4285F4?style=flat&logo=googlescholar&logoColor=white)](https://scholar.google.com/citations?user=yfHyH68AAAAJ)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/nitirajkulkarni)
[![GitHub](https://img.shields.io/badge/GitHub-NitirajKulkarni-181717?style=flat&logo=github&logoColor=white)](https://github.com/NitirajKulkarni)

---

### ⚡ One-Command Deployment

```bash
git clone https://github.com/NitirajKulkarni/capev2-auto-installer.git
cd capev2-auto-installer && chmod +x *.sh
sudo ./install.sh
```

</div>

---

## 📚 Documentation Portal

To keep this guide concise, deep-dive operational documentation has been organized into dedicated guides:

| Document | Description |
| :--- | :--- |
| ❓ [**FAQ & Knowledge Base**](docs/FAQ.md) | Answers to 22+ frequent questions, QuickEdit console traps, drive letters, pending tasks, and snapshot mechanics. |
| 📦 [**Non-PE Analysis Guide**](docs/NON_PE_GUIDE.md) | Complete setup for Office (ODT), WinRAR, 7-Zip, SumatraPDF, Java, Scripts, and bulk Chocolatey installation. |
| 🩺 [**Troubleshooting & Remediation**](docs/TROUBLESHOOTING.md) | Diagnosis and fixes for KVM locks, running snapshot states, qemu delvm commands, and microservice errors. |
| 💻 [**Nested Virtualization Guide**](docs/NESTED_VIRTUALIZATION.md) | Running Ubuntu on VirtualBox, VMware, Hyper-V, Proxmox, and fixing Windows host VBS locks. |
| 🏗️ [**Architecture & Pipeline**](docs/ARCHITECTURE.md) | Deep-dive into the 24-stage state machine, state persistence, and hermetic virtual environments. |
| ⚙️ [**Configuration Reference**](docs/CONFIGURATION.md) | Full schema and customization parameters for `config.toml`. |
| 📖 [**Operator Runbook**](docs/RUNBOOK.md) | Daily health checks, continuous monitoring, and service lifecycle management. |

---

## 🌟 Key Highlights

- 🚀 **100% Zero-Touch Automation**: Eliminates hundreds of fragile manual commands across KVM, libvirt, PostgreSQL/MongoDB, Python virtualenvs, and Windows guest setup.
- 🪟 **Autonomous Windows Provisioning**: Streams genuine Microsoft Evaluation ISOs directly from Microsoft CDNs and builds unattended answer discs (`Autounattend.xml` + WinPE bypasses).
- 🔄 **Deterministic 24-Stage State Machine**: Atomic stages tracked in `state/manifest.json`. Fully resumable after host reboots (`./install.sh --resume`).
- 🛠️ **Autonomous Self-Healing Engine**: Integrated `./repair.sh` diagnoses and repairs broken snapshots, cleans stale PID locks, restores routing tables, and restarts daemons.
- 📦 **Complete Non-PE Format Readiness**: Supports automated bulk deployment for Microsoft Office, WinRAR, 7-Zip, SumatraPDF, Java, AutoIt, and Node.js.
- 🛡️ **Forensic Sandbox Integrity**: Enforces authentic Windows operating systems (strictly blocks stripped Tiny11 builds) to guarantee malware executes realistically.

---

## 🚀 Quick Start Guide

### 1. Standard Installation
```bash
# Automated deployment with Windows 10 Enterprise Evaluation (Recommended):
sudo ./install.sh

# Unattended mode (ideal for CI/CD, cloud-init, and automated infrastructure):
sudo ./install.sh --non-interactive
```

### 2. Clean Reinstall (Full Wipe & Fresh Build)
Wipes previous virtual machines, disks, networks, `/opt/CAPEv2`, and state, then rebuilds from scratch:
```bash
sudo ./clean-install.sh
```

### 3. Automatic Evaluation ISO Streaming
Automatically streams official Microsoft Enterprise Evaluation ISOs with live speed indicators and resume support:
```bash
# Windows 10 Enterprise Evaluation (Gold standard for nested hypervisors):
sudo ./install.sh --auto-download-iso

# Windows 11 Enterprise Evaluation:
sudo ./clean-install.sh --windows-edition win11_eval --auto-download-iso
```

### 4. Resume Interrupted Deployment
If a system reboot or network interruption occurs, resume instantly without losing progress:
```bash
sudo ./install.sh --resume
```

---

## 🪟 Windows Sandbox Provisioning Flow

```
 ┌──────────────────────┐      ┌────────────────────────┐      ┌───────────────────────┐
 │ Official Microsoft   │      │ Dynamic Answer Disc    │      │ KVM / QEMU Virtual    │
 │ Enterprise Eval ISO  │ ───► │ Volume: OEMDRV         │ ───► │ Machine Boot          │
 │ (Win10 or Win11)     │      │ Autounattend.xml + PS1 │      │ (SATA Disk + e1000e)  │
 └──────────────────────┘      └────────────────────────┘      └──────────┬────────────┘
                                                                          │
 ┌──────────────────────┐      ┌────────────────────────┐                 ▼
 │ Clean Snapshot Saved │      │ Restart Guest VM       │      ┌───────────────────────┐
 │ Name: cape-clean     │ ◄─── │ Port 8000 Handshake OK │ ◄─── │ Manual PS1 Execution  │
 │ Configured in kvm.conf│     │ Static: 192.168.250.100│      │ powershell -ep bypass │
 └──────────────────────┘      └────────────────────────┘      └───────────────────────┘
```

### Phase 1: Automated Base OS Setup (Host Orchestrated)
1. Streams genuine Windows Enterprise Evaluation ISO directly from Microsoft.
2. Generates dynamic answer disc (`cape-win-unattend.iso`) mounted as secondary optical drive (Drive `E:` / `D:`).
3. Bypasses TPM 2.0, Secure Boot, RAM/CPU requirements, and Microsoft account prompts (`OOBE\BYPASSNRO`).
4. Windows automatically partitions disk, installs OS, and logs into desktop user `cape`.

### Phase 2: Guest Configuration (`setup-agent.ps1`)
Because Windows enforces User Account Control and execution policy restrictions, execute the configuration script once inside the Windows VM:

1. Open VM console: `virt-viewer -c qemu:///system cape-win` (or connect via VNC).
2. Open **Windows PowerShell as Administrator**.
3. Run the universal 1-liner to configure network, disable Defender, and launch the agent:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force; $s = (Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'setup-agent.ps1' } | Where-Object { Test-Path $_ } | Select-Object -First 1); if ($s) { & $s }
   ```
4. **Restart the VM** to flush network routes and auto-start the agent daemon on boot:
   ```powershell
   Restart-Computer
   ```

### Phase 3: Automated Snapshot & Service Launch (Host Orchestrated)
1. Ubuntu orchestrator polls `http://192.168.250.100:8000/` until `HTTP 200 OK` is received.
2. Automatically captures the live running snapshot (`cape-clean`) with active RAM memory (`<state>running</state>`).
3. Registers snapshot metadata in `/opt/CAPEv2/conf/kvm.conf`.
4. Starts the 4-microservice stack (`cape-rooter`, `cape`, `cape-processor`, `cape-web`) in strict dependency order.

<details>
<summary><b>💡 Click to view detailed guest setup tips & QuickEdit trap prevention</b></summary>

- **Execution Policy**: Never run `.\setup-agent.ps1` without `-ExecutionPolicy Bypass`, or Windows blocks it with `PSSecurityException`.
- **The QuickEdit Trap**: If PowerShell appears frozen on "Installing Python...", click inside the console and press **`Esc`** &rarr; **`Enter`**. Disable QuickEdit in PowerShell Properties to prevent text-selection pausing.
- **Why Rebooting Works**: Rebooting registers `agent.pyw` into Windows Startup, binds static IP `192.168.250.100`, and triggers the host snapshot within 15 seconds.
- **Detailed Guide**: Consult [docs/FAQ.md](docs/FAQ.md) for full screenshots and answers.

</details>

---

## 🛠️ Master CLI Reference Cheat Sheet

| Command | Action | Description |
| :--- | :--- | :--- |
| `sudo ./install.sh` | **Install** | Runs preflight, dependencies, KVM, CAPEv2, and guest provisioning. |
| `sudo ./clean-install.sh` | **Clean Install** | Wipes existing VMs, networks, `/opt/CAPEv2`, and state, then reinstalls fresh. |
| `sudo ./enable-nonpe.sh` | **Enable Non-PE** | Stages WinRAR, 7-Zip, SumatraPDF & script handlers, then snapshots VM. |
| `sudo ./repair.sh` | **Self-Repair** | Automatically repairs running snapshots, stale PID locks, and microservices. |
| `sudo ./diagnose.sh` | **Diagnose** | Audits 11 subsystems (KVM, libvirt, routing, databases, and daemons). |
| `sudo ./diagnose.sh --watch` | **Live Monitor** | Continuous real-time subsystem diagnostic dashboard. |
| `sudo ./status.sh` | **Status** | Displays progress across all 24 stages and active checkpoints. |
| `sudo ./status.sh --drift` | **Drift Check** | Detects configuration drift between files and runtime system state. |
| `sudo ./uninstall.sh --full-reset`| **Full Wipe** | Safely tears down VMs, virtual disks, bridges, and databases. |

---

## 🔄 The 24-Stage State Machine Pipeline

Every stage is atomic, deterministic, and persisted in `state/manifest.json`:

```
 [1] PREFLIGHT          Audit host hardware, virtualization flags, RAM & CPU
 [2] BACKUP             Backup existing network and service configurations
 [3] REPOSITORIES       Refresh APT sources, purge stale locks & configure mirrors
 [4] BASE_PACKAGES      Install system compilers, headers, tmux, and genisoimage
 [5] KVM                Verify/install KVM and load hardware virtualization modules
 [6] LIBVIRT            Configure libvirtd/virtqemud daemons, groups & sockets
 [7] REBOOT_CHECK       Evaluate whether kernel update requires host reboot
 [8] CAPE_REPOSITORY    Clone or update KevReilly/CAPEv2 repository
 [9] CAPE_DEPENDENCIES  Install system libraries (yara, tcpdump, libmagic, libssl)
[10] CAPE_INSTALL       Setup isolated Python 3.12 environment (uv / poetry)
[11] CAPE_CONFIG        Generate customized cuckoo.conf, kvm.conf, and routing.conf
[12] DATABASE           Configure MongoDB / PostgreSQL database backends
[13] SYSTEMD            Install systemd units (cape, cape-web, cape-processor, rooter)
[14] NETWORK            Create isolated analysis network bridge (virbr-cape / 192.168.250.1)
[15] VM_CREATE          Provision virtual disk and libvirt domain (Win10/11 Eval)
[16] VM_INSTALL         Unattended zero-touch Windows setup via OEMDRV answer disc
[17] VM_CONFIG          Harden guest baseline (disable Defender, UAC, firewall, sleep)
[18] AGENT              Bootstrap and verify CAPE HTTP agent daemon on port 8000
[19] SNAPSHOT           Capture clean analysis snapshot (cape-clean) in running state
[20] MACHINERY_CONFIG   Bind guest snapshot metadata into CAPE kvm.conf
[21] CAPE_START         Start all CAPE systemd services in proper dependency order
[22] HEALTH_CHECK       Perform active HTTP, socket, database, and sniffer verification
[23] END_TO_END_TEST    Execute synthetic analysis task validation
[24] FINALIZE           Generate comprehensive Markdown & JSON operational reports
```

---

## 💻 Running Inside a Virtual Machine (Nested Virtualization)

Running your Ubuntu CAPEv2 host inside VirtualBox, VMware, Hyper-V, or Proxmox? Ensure nested virtualization is enabled:

| Hypervisor | Configuration Steps |
| :--- | :--- |
| **Oracle VirtualBox** | VM Settings &rarr; *System* &rarr; *Processor* &rarr; Check **"Enable Nested VT-x/AMD-V"**. |
| **VMware Workstation** | VM Settings &rarr; *Processors* &rarr; Check **"Virtualize Intel VT-x/EPT or AMD-V/RVI"**. |
| **Proxmox VE** | VM Hardware &rarr; *Processor* &rarr; Set CPU Type to **`host`**. |
| **Microsoft Hyper-V** | In PowerShell: `Set-VMProcessor -VMName "<VM>" -ExposeVirtualizationExtensions $true` |

> [!TIP]
> **Windows Host 1-Click Fix (VirtualBox "Green Turtle" / VBS Lock):**  
> If VirtualBox shows a green turtle icon and `/dev/kvm` is missing inside Ubuntu, Windows Hyper-V/VBS is locking hardware virtualization.  
> Run [`enable-windows-virtualization.bat`](enable-windows-virtualization.bat) as Administrator on Windows, select option `[1]`, and reboot.  
> *(See [docs/NESTED_VIRTUALIZATION.md](docs/NESTED_VIRTUALIZATION.md) for complete details).*

---

## 📁 Repository Structure

```
capev2-auto-installer/
├── clean-install.sh            # 🧼 1-Click clean reinstallation wrapper
├── install.sh                  # 🚀 Master installer entry point
├── diagnose.sh                 # 🩺 11-Subsystem diagnostic tool
├── repair.sh                   # 🛠️ Autonomous self-repair engine
├── status.sh                   # 📊 Stage progression & drift checker
├── enable-nonpe.sh             # 📦 Non-PE environment builder & snapshotter
├── uninstall.sh                # 🗑️ Safe resource uninstaller
├── config.toml                 # ⚙️ Master configuration file
├── enable-windows-virtualization.bat # 🪟 Windows VBS / Hyper-V fix script
├── docs/                       # 📚 Dedicated modular documentation portal
│   ├── FAQ.md                  # ❓ 22+ Detailed questions & answers
│   ├── NON_PE_GUIDE.md         # 📦 Office, RAR, 7-Zip & script analysis guide
│   ├── TROUBLESHOOTING.md      # 🩺 Diagnosis & remediation runbook
│   ├── NESTED_VIRTUALIZATION.md# 💻 Hypervisor compatibility guide
│   ├── ARCHITECTURE.md         # 🏗️ State machine architecture
│   ├── CONFIGURATION.md        # ⚙️ Configuration options reference
│   └── RUNBOOK.md              # 📖 Operational management procedures
├── src/cape_auto/              # 🐍 Core Python orchestration engine
└── templates/                  # 📄 Systemd, network, and unattended XML templates
```

---

## 👤 Author & Maintainer

### [**Nitiraj V. Kulkarni — AI Safety & Cybersecurity Researcher**](https://nitirajkulkarni.in/)

- 🌐 **Website:** [nitirajkulkarni.in](https://nitirajkulkarni.in/)
- 🎓 **Google Scholar:** [Citations & Publications](https://scholar.google.com/citations?user=yfHyH68AAAAJ)
- 💼 **LinkedIn:** [linkedin.com/in/nitirajkulkarni](https://www.linkedin.com/in/nitirajkulkarni)
- 🐙 **GitHub:** [@NitirajKulkarni](https://github.com/NitirajKulkarni)
- 📦 **Repository:** [capev2-auto-installer](https://github.com/NitirajKulkarni/capev2-auto-installer)

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see the [LICENSE](LICENSE) file for complete details. Compatible with the official [CAPEv2 Sandbox](https://github.com/kevoreilly/CAPEv2) ecosystem.
