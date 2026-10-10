<div align="center">

# 🦅 CAPEv2 Universal Automated Installer & Malware Sandbox Orchestrator

**A self-healing, zero-touch, automated installation and lifecycle engine for CAPEv2 Sandbox on Ubuntu hosts.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ubuntu: 24.04 | 22.04 LTS](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2022.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Guest: Zero--Touch Unattended](https://img.shields.io/badge/Windows-Zero--Touch%20Unattended-0078D6?logo=windows&logoColor=white)](templates/windows/)

**Author & Maintainer:** [**Nitiraj V. Kulkarni — AI Safety & Cybersecurity Researcher**](https://nitirajkulkarni.in/)  
[![Website](https://img.shields.io/badge/Website-nitirajkulkarni.in-0078D6?style=flat&logo=googlechrome&logoColor=white)](https://nitirajkulkarni.in/)
[![Google Scholar](https://img.shields.io/badge/Google_Scholar-Citations-4285F4?style=flat&logo=googlescholar&logoColor=white)](https://scholar.google.com/citations?user=yfHyH68AAAAJ)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/nitirajkulkarni)
[![GitHub](https://img.shields.io/badge/GitHub-NitirajKulkarni-181717?style=flat&logo=github&logoColor=white)](https://github.com/NitirajKulkarni)

---

### ⚡ Zero to CAPEv2 in One Command

```bash
git clone https://github.com/NitirajKulkarni/capev2-auto-installer.git
cd capev2-auto-installer && chmod +x *.sh
sudo ./install.sh
```

</div>

---

## 📖 Overview

Designed to accelerate dynamic malware analysis and threat intelligence, this **CAPEv2 Sandbox Auto-Installer** solves the notoriously fragile manual deployment process of setting up isolated environments. Developed out of advanced AI safety and cybersecurity research by Nitiraj Kulkarni, this orchestration engine provides a 100% zero-touch, self-healing framework for deploying a military-grade malware analysis sandbox on modern Ubuntu systems.

When deploying CAPEv2 manually, security researchers and SOC operators frequently run into:
- ❌ Missing nested hardware virtualization flags (`/dev/kvm`).
- ❌ Host package lock contention (`/var/lib/dpkg/lock`).
- ❌ Python version mismatches (e.g., Python 3.14 wheel incompatibilities with `python-flirt`).
- ❌ Manual, tedious Windows installation screens requiring VNC viewer interaction.
- ❌ Brittle bash scripts that crash halfway through and force a complete manual restart.

This repository eliminates all manual friction by wrapping CAPEv2 into a **deterministic 24-stage state machine** with **autonomous environment discovery**, **streaming ISO provisioning**, **unattended zero-touch Windows guest installation**, and **built-in self-healing**.

---

## 🚀 Quick Start Guide

### 1. Fresh Full Installation
```bash
# Standard automated installation (Windows 10 Enterprise Eval by default):
sudo ./install.sh

# Unattended / non-interactive (ideal for CI/CD and cloud-init):
sudo ./install.sh --non-interactive
```

### 2. Clean Reinstall (Full Wipe & Fresh Rebuild)
Need to wipe an old or broken deployment and start completely fresh? Use the clean install command:
```bash
# Wipes previous VMs, disks, networks, /opt/CAPEv2, and state, then installs fresh:
sudo ./clean-install.sh

# Or via install.sh flag:
sudo ./install.sh --clean-install
```

### 3. Automatic Windows Evaluation ISO Download
No need to manually find, download, or transfer multi-gigabyte ISOs. The installer streams official Microsoft Evaluation ISOs directly from Microsoft's CDN with live speed and resume support:
```bash
# Windows 10 Enterprise Evaluation (Recommended - gold standard for malware analysis & nested VMs):
sudo ./install.sh --auto-download-iso

# Or with clean reinstallation:
sudo ./clean-install.sh --windows-edition win10_eval --auto-download-iso

# Windows 11 Enterprise Evaluation:
sudo ./clean-install.sh --windows-edition win11_eval --auto-download-iso
```

> [!TIP]
> **Running inside VirtualBox or VMware?**
> We strongly recommend **`win10_eval`** (the default). Windows 10 Enterprise Evaluation boots in standard BIOS mode and uses ~3.5 GB RAM, avoiding VirtualBox nested SMM/TPM crashes and host memory exhaustion. The built-in **Resource Guard** automatically scales memory and vCPUs so your Ubuntu host retains plenty of RAM.

### 4. Resume After Interruption or Reboot
If host updates or kernel drivers require a system reboot, simply resume without losing progress:
```bash
sudo ./install.sh --resume
```

---

## 🪟 100% Unattended Windows Guest Automation

The installer provisions a complete analysis virtual machine with **zero manual clicks**:

```
 ┌──────────────────────┐      ┌────────────────────────┐      ┌───────────────────────┐
 │ Official Microsoft   │      │ Dynamic Answer Disc    │      │ KVM / QEMU Virtual    │
 │ Enterprise Eval ISO  │ ───► │ Volume: OEMDRV         │ ───► │ Machine Auto-Boot     │
 │ (Win10 or Win11)     │      │ Autounattend.xml + PS1 │      │ (SATA Disk + e1000e)  │
 └──────────────────────┘      └────────────────────────┘      └──────────┬────────────┘
                                                                          │
 ┌──────────────────────┐      ┌────────────────────────┐                 ▼
 │ Clean Snapshot Saved │      │ Guest Agent Listening  │      ┌───────────────────────┐
 │ Name: cape-clean     │ ◄─── │ Port 8000 Verified     │ ◄─── │ FirstLogon Script     │
 │ Configured in kvm.conf│     │ Static: 192.168.250.100│      │ Hardens Sandbox & IP  │
 └──────────────────────┘      └────────────────────────┘      └───────────────────────┘
```

1. **Automatic Download**: Downloads genuine Microsoft Windows Enterprise Evaluation ISOs with chunked resume support and live MB/s progress.
2. **OEMDRV Answer Disc**: Automatically generates `cape-unattend.iso` containing `Autounattend.xml` and attaches it as a secondary optical drive.
3. **Hardware Bypass for Win11**: Injects WinPE bypasses for TPM 2.0, Secure Boot, RAM, and CPU checks.
4. **Out-of-the-Box Driver Compatibility**: Provisions virtual disks over native SATA AHCI and network over Intel `e1000e`, eliminating third-party VirtIO driver dependencies during Windows setup.
5. **FirstLogon Automation (`setup-agent.ps1`)**:
   - Assigns static IP `192.168.250.100/24` on gateway `192.168.250.1`.
   - Hardens the guest baseline: disables Windows Defender real-time monitoring, UAC, Windows Update, Firewall, and sleep timeouts.
   - Deploys an HTTP agent daemon on `http://192.168.250.100:8000/` registered in Windows Startup.
6. **Automatic Verification & Snapshot**: Orchestrator confirms `HTTP 200 OK` from the guest agent, captures snapshot `cape-clean`, and configures CAPE `kvm.conf`.

> [!CAUTION]
> **Strict Policy: Strictly NO Tiny11 or Stripped Custom OS Images**  
> Malware analysis strictly requires **authentic, full-fidelity Windows**.  
> Stripped builds (such as Tiny11, Tiny10, GhostSpectre, or ReviOS) remove vital components:
> - **Windows Defender & AMSI**: Malware checks for Defender presence; if missing, samples fail to execute or evade detection.
> - **Event Tracing for Windows (ETW)**: Kernel trace providers disabled, blinding behavioral analyzers.
> - **WMI Providers & Namespaces**: Evasion queries crash when WMI providers are stripped.
> - **Task Scheduler & BITS**: Persistence routines fail to execute.
> 
> The installer actively blocks Tiny11 images to guarantee forensic fidelity.

---

## 🛠️ CLI Command Cheat Sheet

| Command | Action | Description |
| :--- | :--- | :--- |
| `sudo ./install.sh` | **Install** | Runs discovery, dependencies, KVM, CAPE, and guest provisioning. |
| `sudo ./clean-install.sh` | **Clean Install** | Wipes previous VMs, disks, networks, `/opt/CAPEv2`, and state, then reinstalls. |
| `sudo ./install.sh --clean-install` | **Clean Install** | Same as `./clean-install.sh` (can combine with custom options). |
| `sudo ./install.sh --resume` | **Resume** | Resumes seamlessly from the last recorded atomic checkpoint. |
| `sudo ./diagnose.sh` | **Diagnose** | Audits 11 subsystems (KVM, libvirt, network, PostgreSQL/MongoDB, services). |
| `sudo ./diagnose.sh --watch` | **Live Monitor** | Real-time continuous subsystem status dashboard. |
| `sudo ./repair.sh` | **Self-Repair** | Automatically heals broken services, stale locks, and network interfaces. |
| `sudo ./status.sh` | **Status** | Displays state of all 24 stages and active checkpoints. |
| `sudo ./status.sh --drift` | **Drift Check** | Detects drift between configuration files and runtime system state. |
| `sudo ./uninstall.sh --full-reset` | **Full Wipe** | Complete uninstall including virtual disks, networks, and databases. |

---

## 🔄 The 24-Stage State Machine Pipeline

Every stage is atomic, logged, and tracked in `state/manifest.json`:

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
[19] SNAPSHOT           Capture clean analysis snapshot (cape-clean)
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
| **VMware Workstation / Player** | Power off VM &rarr; *Virtual Machine Settings* &rarr; *Processors* &rarr; Check **"Virtualize Intel VT-x/EPT or AMD-V/RVI"**. |
| **Oracle VirtualBox** | Power off VM &rarr; *Settings* &rarr; *System* &rarr; *Processor* &rarr; Check **"Enable Nested VT-x/AMD-V"**. |
| **Proxmox VE** | Select VM &rarr; *Hardware* &rarr; *Processors* &rarr; Set CPU Type to **`host`**. |
| **Microsoft Hyper-V** | In Administrator PowerShell on Windows: <br>`Set-VMProcessor -VMName "<Your-Ubuntu-VM>" -ExposeVirtualizationExtensions $true` |

> [!TIP]
> **Windows 10/11 Host Automated Fix (VirtualBox / VMware):**  
> If VirtualBox on Windows shows an icon of a green turtle (Snail Execution Mode) and `/dev/kvm` is missing inside Ubuntu, Windows Hyper-V or Virtualization-Based Security (VBS) is locking the CPU.  
> **1-Click Fix:** Run [`enable-windows-virtualization.bat`](enable-windows-virtualization.bat) on Windows as Administrator, choose option `[1]`, and reboot.

---

## ❓ FAQ & Troubleshooting

### Q: The installer timed out at "Awaiting guest agent...". What happened?
The script is designed to be 100% zero-touch via `autounattend.xml`, but sometimes Windows 10/11 aggressive network checks ("Let's connect you to a network") ignore the OOBE skip commands. If it gets stuck on these screens, the automated script never runs.

**How to manually configure and resume:**
1. Open the VM console on your Ubuntu host: `virt-viewer -c qemu:///system cape-win`
2. If Windows is asking for setup information, click Next/Skip until you reach the Desktop.
3. Open **Windows PowerShell** as **Administrator** (Right-click -> Run as Administrator).
4. Run this smart-command to automatically find and execute the automated setup script from the virtual CD-ROM (even if the drive letter isn't D:):
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process -Force; $s = (Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'setup-agent.ps1' } | Where-Object { Test-Path $_ } | Select-Object -First 1); if ($s) { & $s }
   ```
   > **⚠️ Warning (The QuickEdit Trap):** If you accidentally click inside the blue PowerShell window, Windows will enter "Select" mode and **freeze the installation script**! If it seems stuck on "Installing Python" for more than 1 minute, press `Esc` and `Enter` on your keyboard to unfreeze it.

5. Wait for it to print `Guest configuration complete!`.
6. Go back to your Ubuntu host and run: `sudo ./install.sh --resume`

### Q: Why does the PowerShell script say "Access is denied" when setting the IP?
You opened PowerShell as a standard user. You **must** right-click the PowerShell icon and select **Run as Administrator**. The script requires admin privileges to configure the firewall and network adapters.

### Q: I wiped the VM using `virsh undefine`, and it deleted the 5GB ISO! Do I have to re-download it?
No, the latest version of this installer automatically isolates the downloaded ISO into a protected folder (`/var/lib/cape-isos/`). Now, if you run `virsh undefine cape-win --remove-all-storage`, libvirt will only delete the virtual hard drive and **will not** touch the ISO.

### Q: A malware analysis has been running for 5 minutes, is it stuck?
No! CAPEv2 takes an average of 3 to 6 minutes to fully execute a malware payload in the sandbox, record all API calls, generate pcap files, extract payloads, and generate the final report. This is completely normal. 

---

## ⚙️ Configuration File (`config.toml`)

Customize your deployment in [`config.toml`](config.toml). Sane, secure defaults are provided:

```toml
[installation]
cape_root = "/opt/CAPEv2"
cape_user = "cape"
non_interactive = false
auto_repair = true
max_repair_attempts = 3

[network]
mode = "isolated"
subnet = "192.168.250.0/24"
gateway = "192.168.250.1"
vm_ip_start = "192.168.250.100"
libvirt_network_name = "cape-analysis"
web_port = 8000

[guest]
enabled = true
name = "cape-win"
windows_edition = "win10_eval"     # "win10_eval" or "win11_eval"
auto_download_iso = true          # Automatically downloads official Microsoft ISO
disk_bus = "sata"                 # Out-of-the-box Windows driver compatibility
network_model = "e1000e"          # Out-of-the-box Intel network compatibility
disk_size_gb = 80
memory_mb = 8192
vcpus = 4
snapshot_name = "cape-clean"
install_timeout_minutes = 35

[guest.agent]
enabled = true
port = 8000
```

---



## 📁 Repository Structure

```
capev2-auto-installer/
├── clean-install.sh            # 🧼 1-Click clean reinstallation wrapper
├── install.sh                  # 🚀 Master installer entry point
├── diagnose.sh                 # 🩺 11-Subsystem diagnostic tool
├── repair.sh                   # 🛠️ Autonomous self-repair engine
├── status.sh                   # 📊 Stage progression & drift checker
├── uninstall.sh                # 🗑️ Safe resource uninstaller
├── config.toml                 # ⚙️ Master configuration file
├── enable-windows-virtualization.bat # 🪟 Windows VBS / Hyper-V fix script
├── docs/                       # 📚 Architecture, configuration & runbooks
├── src/cape_auto/              # 🐍 Core Python orchestration engine
├── templates/                  # 📄 Systemd, network, and unattended XML templates
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
