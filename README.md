<div align="center">

# 🦅 CAPEv2 Universal Automated Installer & Malware Sandbox Orchestrator

**A self-healing, zero-touch, automated installation and lifecycle engine for CAPEv2 Sandbox on Ubuntu hosts.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Ubuntu: 24.04 | 22.04 LTS](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2022.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Guest: Answer Disc Provisioning](https://img.shields.io/badge/Windows-Answer%20Disc%20Provisioning-0078D6?logo=windows&logoColor=white)](templates/windows/)

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

## 🪟 Windows Guest Provisioning & Mandatory Manual Agent Setup

The installer provisions the virtual machine and automated answer disc, after which you execute the guest configuration script manually inside the Windows VM.

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

---

### 📋 Sequential Deployment Flow

The guest deployment process is split into three clean phases:

#### Phase 1: Automated Base OS Setup (Host Orchestrated)
1. **Evaluation ISO Streaming**: Automatically downloads genuine Microsoft Windows Enterprise Evaluation ISOs with live MB/s progress and chunked resume support.
2. **Dynamic Answer Disc (OEMDRV)**: Generates `cape-unattend.iso` containing `Autounattend.xml` and `setup-agent.ps1`, attached as a secondary optical drive (drive `E:` or `D:`).
3. **Hardware & OOBE Bypasses**: Injects WinPE bypasses for Windows 11 TPM 2.0, Secure Boot, RAM, CPU checks, and OOBE network requirement (`BypassNRO`).
4. **Hardware Stability**: Configures virtual disks over native SATA AHCI and networking over Intel `e1000e`, eliminating third-party VirtIO driver dependencies during setup.
5. **Base Installation**: Windows automatically partitions the disk, installs the OS, and boots to the desktop with autologon user `cape` (Password: `cape`).

---

#### Phase 2: Mandatory Manual Guest Configuration (`setup-agent.ps1`)

> [!IMPORTANT]
> **The guest agent setup script does NOT run automatically.**  
> Windows default security policies, User Account Control (UAC), and PowerShell execution restrictions (`Restricted`) prevent automatic first-logon background script runs.  
> Once Windows finishes setup and displays the Desktop, you **must run `setup-agent.ps1` manually in Administrator PowerShell**.

#### Step-by-Step Guest Execution Guide:

1. **Access the Windows Console:**  
   Open the VM display on your Ubuntu host:
   ```bash
   virt-viewer -c qemu:///system cape-win
   ```
   *(Or connect via any VNC client to the host's VNC port).*

2. **Open PowerShell as Administrator:**  
   Click the Windows Start menu &rarr; Type `powershell` &rarr; Right-click **Windows PowerShell** &rarr; Select **Run as Administrator**.

3. **Execute the Setup Script with Execution Policy Bypass:**  
   Navigate to the mounted virtual CD-ROM drive (usually `E:` or `D:`) and run:
   ```powershell
   # If your answer disc is on drive E:
   E:
   powershell -ExecutionPolicy Bypass -File .\setup-agent.ps1
   ```
   *Alternatively, run this universal 1-liner that auto-detects the drive regardless of drive letter:*
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force; $s = (Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'setup-agent.ps1' } | Where-Object { Test-Path $_ } | Select-Object -First 1); if ($s) { & $s }
   ```

   > [!WARNING]
   > Do **NOT** run `.\setup-agent.ps1` directly without bypassing execution policy! Windows will block it with:  
   > `File ... cannot be loaded because running scripts is disabled on this system (PSSecurityException: UnauthorizedAccess)`.

4. **Restart the Windows VM (Mandatory to Trigger Detection & Snapshot):**  
   Once the script finishes and outputs `[+] Guest configuration complete!`, restart the Windows VM:
   ```powershell
   Restart-Computer
   ```
   *(Or from your Ubuntu host terminal: `virsh reboot cape-win`)*.

   > [!TIP]
   > **Why restarting the VM makes the installer detect the agent:**
   > - **Clean Network Binding:** Restarting cleanly applies the static IP (`192.168.250.100`), flushing any transient DHCP leases or half-open socket states.
   > - **Automatic Startup Daemon:** The script registers `agent.pyw` into the Windows Startup folder (`%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup`). When Windows boots up and auto-logs into the `cape` user, it automatically launches the agent daemon in the background listening on port 8000.
   > - **Instant Handshake:** Within ~10 to 15 seconds after rebooting, the Ubuntu orchestrator detects the `HTTP 200 OK` response on `http://192.168.250.100:8000/`, stops polling, and automatically captures the clean baseline snapshot (`cape-clean`)!

#### What `setup-agent.ps1` Automates Inside the Guest:
- 🌐 **Static Network Binding:** Configures static IP `192.168.250.100`, subnet mask `255.255.255.0`, gateway `192.168.250.1`, and DNS `1.1.1.1`.
- 🛡️ **Forensic Hardening:** Disables Windows Defender (real-time monitoring, cloud protection, automatic sample submission), UAC, Windows Firewall across all profiles, and sleep/display timers.
- 🐍 **Agent Deployment:** Deploys an isolated Python runtime and launches the official CAPEv2 HTTP Agent daemon on `http://192.168.250.100:8000/` registered in Windows Startup.
- ✅ **Confirmation:** Prints `[+] Guest configuration complete! CAPE Agent is active on port 8000.`

---

#### Phase 3: Automated Snapshot & Deployment Finalization (Host Orchestrated)
1. **Agent Handshake**: The Ubuntu orchestrator continuously polls `http://192.168.250.100:8000/` until it receives `HTTP 200 OK`.
2. **Clean Snapshot Capture**: As soon as the agent responds, the orchestrator pauses the VM and captures the clean baseline snapshot:
   ```bash
   virsh snapshot-create-as cape-win cape-clean --disk-only --atomic
   ```
3. **Machinery Binding**: Automatically registers snapshot metadata into `/opt/CAPEv2/conf/kvm.conf`.
4. **Stack Launch**: Starts all CAPEv2 systemd microservices (`cape.service`, `cape-web.service`, `cape-processor.service`, `rooter.service`) in proper dependency order.

---

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

## ❓ Detailed FAQ & Troubleshooting Guide

### Q1: Why does running `.\setup-agent.ps1` fail with `PSSecurityException: UnauthorizedAccess`?
**Cause:** Windows PowerShell defaults to `Restricted` execution policy, which blocks running any external scripts (`.ps1`).  
**Fix:** You must execute the script with `-ExecutionPolicy Bypass`. In PowerShell (Admin):
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-agent.ps1
```
*Or set the execution policy for your current PowerShell session first:*
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
.\setup-agent.ps1
```

---

### Q2: Which drive letter is the setup script on? (`D:`, `E:`, or `F:`)?
**Explanation:** Windows assigns drive letters to CD-ROM drives dynamically depending on partitions.  
- If Windows only has a `C:` drive, the answer disc is usually `D:`.
- If Windows has a recovery partition or second disk, the answer disc is often `E:`.  
**How to check:** In PowerShell, run:
```powershell
Get-PSDrive -PSProvider FileSystem
```
Look for the drive labeled `OEMDRV` or `cuckoo`. You can switch to that drive (e.g. `E:`) and run `dir` to see `setup-agent.ps1`.  
**Universal 1-Liner:** If you don't want to check drive letters, use this command—it scans all drives automatically:
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force; $s = (Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'setup-agent.ps1' } | Where-Object { Test-Path $_ } | Select-Object -First 1); if ($s) { & $s }
```

---

### Q3: Why does PowerShell freeze or stop progressing during script execution? (The QuickEdit Trap)
**Cause:** The Windows console has **QuickEdit Mode** enabled by default. If you click anywhere inside the blue PowerShell console window, Windows enters text-selection mode and **pauses the entire execution thread**!  
**Fix:**
1. If the script appears stuck (e.g., waiting on "Installing Python..." for over 2 minutes), click the window and press **`Esc`** followed by **`Enter`**. Output will immediately resume scrolling.
2. To permanently disable QuickEdit: Right-click the PowerShell title bar &rarr; *Properties* &rarr; *Options* tab &rarr; Uncheck **QuickEdit Mode** &rarr; Click *OK*.

---

### Q4: Why does the PowerShell script say "Access is denied" when setting the IP address?
**Cause:** You launched PowerShell as a standard user instead of Administrator. Network configuration and Defender remediation require administrative privileges.  
**Fix:** Close the window, open the Start menu, type `powershell`, right-click **Windows PowerShell**, and click **Run as Administrator**.

---

### Q5: The script finished in Windows, but Ubuntu still waits at "Awaiting guest agent on 192.168.250.100:8000...". What should I do?
**Fix: Simply restart the Windows VM!**  
In the Windows guest PowerShell, run:
```powershell
Restart-Computer
```
Or from your Ubuntu host terminal:
```bash
virsh reboot cape-win
```

**Why restarting makes it detect immediately:**
1. **Flushes Network Stack:** On Windows, assigning the static IP `192.168.250.100` during an active session can leave adapter routes unrefreshed on the host bridge. A reboot cleanly binds the static IP and routing table with `virbr-cape`.
2. **Auto-starts Agent Daemon:** `setup-agent.ps1` places `agent.pyw` into the Windows Startup folder (`%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup`). When the VM reboots and autologon logs into user `cape`, Windows automatically launches the agent daemon in the user session.
3. **Instant Snapshot Trigger:** As soon as Windows boots back up (~10–15 seconds), the Ubuntu orchestrator receives `HTTP/1.0 200 OK`, immediately captures the `cape-clean` baseline snapshot, and launches the CAPEv2 systemd microservices!

**How to verify from the Ubuntu host:**
In a separate terminal on your Ubuntu host, test connectivity:
```bash
curl -I http://192.168.250.100:8000/
```
- If it returns `HTTP/1.0 200 OK`, the agent is alive and the installer will immediately detect it and capture the snapshot.
- If it returns `Connection refused` or times out, restarting the VM via `virsh reboot cape-win` will launch the agent on boot.

---

### Q6: How do I open the Windows guest graphical desktop from Ubuntu?
If you are running on a local desktop or via SSH with X11 forwarding:
```bash
virt-viewer -c qemu:///system cape-win
```
If you are on a headless server without GUI, use VNC:
```bash
virsh vncdisplay cape-win
```
*(e.g., `:0` corresponds to port `5900`, `:1` to `5901`). Connect using any VNC viewer (Remmina, TigerVNC, RealVNC).*

---

### Q7: Can I re-run `setup-agent.ps1` if something went wrong or the VM rebooted?
**Yes.** `setup-agent.ps1` is completely idempotent. You can re-run it multiple times without issues. It will verify the static IP, re-check Defender disablement, and restart the agent on port 8000.

---

### Q8: How to verify that the CAPE agent is listening inside Windows?
Inside the Windows guest PowerShell:
```powershell
netstat -ano | findstr 8000
```
Or test via PowerShell:
```powershell
Test-NetConnection -Port 8000 -ComputerName 127.0.0.1
```
If `TcpTestSucceeded : True`, the CAPE agent HTTP server is active and listening.

---

### Q9: What if Windows setup prompts for a Microsoft Account or internet during installation?
If Windows setup pauses at "Let's connect you to a network":
1. Press `Shift + F10` to open a command prompt.
2. Type `OOBE\BYPASSNRO` and press Enter. The VM will reboot.
3. Upon reboot, click **"I don't have internet"**, then select **"Continue with limited setup"**.
4. Set the username to `cape` and password to `cape`.

---

### Q10: A malware analysis task has been running for 5 minutes, is it stuck?
No! CAPEv2 takes an average of 3 to 6 minutes to fully execute a malware payload in the sandbox, record all API calls, generate PCAP files, extract payloads, and generate the final report. This is completely normal operational behavior.

---

### Q11: Why is my submitted task stuck on 'Pending' on the web dashboard while the VM does nothing?
**Root Cause:**  
The CAPEv2 Web UI (`cape-web.service`) only creates the task record in the database. It does not interact with KVM.  
The actual task execution and VM lifecycle is managed by **`cape.service`** (the master sandbox scheduler running `cuckoo.py`), and result extraction is handled by **`cape-processor.service`** (`utils/process.py`). If either daemon is stopped or inactive, tasks remain in `pending` forever and the VM will never be started or reverted!

**Instant Fix:**  
Ensure all four CAPEv2 microservices are active:
```bash
# 1. Enable and start all microservices:
sudo systemctl enable --now cape-rooter cape cape-processor cape-web

# 2. Or let the autonomous repair engine fix and start them:
sudo ./repair.sh

# 3. Or use the master CLI launcher:
cape-start
```

**Verify Service Health:**
```bash
cape-status
# Or via systemctl:
sudo systemctl status cape-rooter cape cape-processor cape-web --lines=0
```
All four services must report `active (running)`.

**Watch Live Task Scheduling:**  
Once `cape.service` is active, watch the logs as it immediately claims the pending task:
```bash
sudo journalctl -u cape.service -f -n 30
# Or via logfile:
tail -f /opt/CAPEv2/log/cuckoo.log
```
You will immediately observe KVM reverting `cape-win` to `cape-clean`, launching the VM, executing the sample, and advancing the task on the dashboard from **`pending` &rarr; `running` &rarr; `completed`**!

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
