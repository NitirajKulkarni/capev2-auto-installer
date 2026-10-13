# ❓ Frequently Asked Questions (FAQ) & Knowledge Base

Welcome to the comprehensive CAPEv2 Automated Installer Knowledge Base. This guide addresses common questions, operational caveats, and troubleshooting patterns encountered when deploying and maintaining CAPEv2 with KVM/QEMU Windows sandboxes.

---

## 📑 Table of Contents

- [🚀 Installation & Preflight](#-installation--preflight)
  - [Q1: Does this installer work on Ubuntu 24.04 and 22.04 LTS?](#q1-does-this-installer-work-on-ubuntu-2404-and-2204-lts)
  - [Q2: Where does the installer download Windows ISOs from?](#q2-where-does-the-installer-download-windows-isos-from)
  - [Q3: Why is Windows 10 Enterprise Evaluation recommended over Windows 11?](#q3-why-is-windows-10-enterprise-evaluation-recommended-over-windows-11)
  - [Q4: Why does the installer block Tiny11 or stripped Windows images?](#q4-why-does-the-installer-block-tiny11-or-stripped-windows-images)
- [🪟 Windows Guest Provisioning & Agent Setup](#-windows-guest-provisioning--agent-setup)
  - [Q5: Why do I need to run `setup-agent.ps1` manually inside the Windows VM?](#q5-why-do-i-need-to-run-setup-agentps1-manually-inside-the-windows-vm)
  - [Q6: Why does running `.\setup-agent.ps1` fail with `PSSecurityException: UnauthorizedAccess`?](#q6-why-does-running-setup-agentps1-fail-with-pssecurityexception-unauthorizedaccess)
  - [Q7: Which drive letter is the answer disc mounted on? (`D:`, `E:`, or `F:`)](#q7-which-drive-letter-is-the-answer-disc-mounted-on-d-e-or-f)
  - [Q8: Why does PowerShell freeze or pause during guest installation? (The QuickEdit Trap)](#q8-why-does-powershell-freeze-or-pause-during-guest-installation-the-quickedit-trap)
  - [Q9: Why does the script report "Access is denied" when configuring the network interface?](#q9-why-does-the-script-report-access-is-denied-when-configuring-the-network-interface)
  - [Q10: The script finished, but Ubuntu still waits at "Awaiting guest agent...". What do I do?](#q10-the-script-finished-but-ubuntu-still-waits-at-awaiting-guest-agent-what-do-i-do)
  - [Q11: How do I access the Windows graphical console from Ubuntu?](#q11-how-do-i-access-the-windows-graphical-console-from-ubuntu)
  - [Q12: What if Windows pauses asking for a Microsoft Account or internet connection?](#q12-what-if-windows-pauses-asking-for-a-microsoft-account-or-internet-connection)
- [⚙️ Sandbox Operations & Task Scheduling](#️-sandbox-operations--task-scheduling)
  - [Q13: Why are my submitted malware tasks stuck in 'Pending' on the web dashboard?](#q13-why-are-my-submitted-malware-tasks-stuck-in-pending-on-the-web-dashboard)
  - [Q14: An analysis task has been running for 4 minutes. Is the VM stuck?](#q14-an-analysis-task-has-been-running-for-4-minutes-is-the-vm-stuck)
  - [Q15: How do I view live real-time analysis logs while a task runs?](#q15-how-do-i-view-live-real-time-analysis-logs-while-a-task-runs)
- [📸 VM Snapshot & State Management](#-vm-snapshot--state-management)
  - [Q16: Why did CAPEv2 crash with `Snapshot 'cape-clean' is not in a 'running' state`?](#q16-why-did-capev2-crash-with-snapshot-cape-clean-is-not-in-a-running-state)
  - [Q17: Why did libvirt report `Snapshot 'cape-clean' already exists in one or more devices`?](#q17-why-did-libvirt-report-snapshot-cape-clean-already-exists-in-one-or-more-devices)
- [📦 Non-PE & File Formats Support](#-non-pe--file-formats-support)
  - [Q18: Why did my Excel or Word analysis fail with `Unable to find any EXCEL.EXE executable`?](#q18-why-did-my-excel-or-word-analysis-fail-with-unable-to-find-any-excelexe-executable)
  - [Q19: Why did my RAR analysis fail with `Unable to find any WinRAR.exe executable`?](#q19-why-did-my-rar-analysis-fail-with-unable-to-find-any-winrarexe-executable)
  - [Q20: How do I bulk install all Non-PE software suites automatically?](#q20-how-do-i-bulk-install-all-non-pe-software-suites-automatically)
- [🛠️ Self-Repair & Maintenance](#️-self-repair--maintenance)
  - [Q21: How do I recover after an unexpected host reboot or system crash?](#q21-how-do-i-recover-after-an-unexpected-host-reboot-or-system-crash)
  - [Q22: What if `cape` fails with `ModuleNotFoundError: No module named 'libvirt'`?](#q22-what-if-cape-fails-with-modulenotfounderror-no-module-named-libvirt)

---

## 🚀 Installation & Preflight

### Q1: Does this installer work on Ubuntu 24.04 and 22.04 LTS?
**Yes.** The orchestrator automatically detects your distribution version and applies the proper dependency trees:
- **Ubuntu 24.04 LTS**: Manages Python 3.12 hermetic virtual environments via `uv`, accommodates modular libvirt daemons (`virtqemud`, `virtnetworkd`), and installs updated QEMU packages.
- **Ubuntu 22.04 LTS**: Accommodates system Python 3.10 and monolithic `libvirtd` socket architecture.

### Q2: Where does the installer download Windows ISOs from?
The orchestrator streams authentic Windows Evaluation ISOs directly from **Microsoft's Official Content Delivery Network (CDN)** (`go.microsoft.com` / `software-download.microsoft.com`).
- No untrusted mirrors or third-party file-sharing sites are ever used.
- Downloads support chunked streaming, SHA-256 integrity verification, and automatic resume if interrupted.

### Q3: Why is Windows 10 Enterprise Evaluation recommended over Windows 11?
While Windows 11 is supported, **Windows 10 Enterprise Evaluation (`win10_eval`)** is the gold standard for nested virtualization and automated sandboxing:
1. **Resource Footprint**: Windows 10 runs smoothly on 3.5 to 4 GB RAM, whereas Windows 11 requires 8 GB+ RAM and higher CPU overhead.
2. **Hypervisor Stability**: Windows 10 uses standard BIOS/MBR boot, avoiding nested UEFI/TPM 2.0 virtualization crashes inside VirtualBox and older VMware hosts.
3. **Malware Targeting**: Over 85% of commodity malware is specifically compiled for Windows 10/7 environments and behaves consistently.

### Q4: Why does the installer block Tiny11 or stripped Windows images?
Malware analysis strictly requires **authentic, full-fidelity operating system components**:
- **Evasion Detection**: Modern malware actively checks for the presence of Windows Defender, specific registry hives, and system DLLs. If they are absent, malware enters dormancy and evades analysis.
- **Event Tracing for Windows (ETW)**: Stripped OS builds disable kernel event providers, completely blinding behavioral monitors.
- **WMI & Scripting Engines**: Evasion scripts query WMI namespaces (`root\cimv2`). Stripped OS images crash during execution.

---

## 🪟 Windows Guest Provisioning & Agent Setup

### Q5: Why do I need to run `setup-agent.ps1` manually inside the Windows VM?
Windows default security policies, User Account Control (UAC), and PowerShell execution restrictions prevent unauthenticated, automated execution of administrative scripts during the first interactive logon.  
By executing `setup-agent.ps1` once inside the VM, you ensure:
1. Administrator rights are explicitly granted.
2. Static IP binding (`192.168.250.100`) binds cleanly to the network interface.
3. The official CAPE Agent daemon is registered in the Startup folder.

### Q6: Why does running `.\setup-agent.ps1` fail with `PSSecurityException: UnauthorizedAccess`?
**Cause**: Windows PowerShell enforces a `Restricted` execution policy by default, preventing execution of any script files.  
**Fix**: Execute PowerShell with `-ExecutionPolicy Bypass`:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-agent.ps1
```
Or run this universal 1-liner in Administrator PowerShell:
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force; .\setup-agent.ps1
```

### Q7: Which drive letter is the answer disc mounted on? (`D:`, `E:`, or `F:`)
Windows assigns drive letters dynamically depending on whether recovery partitions exist:
- If Windows only has a `C:` partition, the virtual CD-ROM drive is `D:`.
- If a recovery or system partition exists, the drive is typically `E:`.

**Universal Auto-Detect 1-Liner:**
Run this in Windows Administrator PowerShell to automatically search all drives and execute the script:
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force; $s = (Get-PSDrive -PSProvider FileSystem | ForEach-Object { Join-Path $_.Root 'setup-agent.ps1' } | Where-Object { Test-Path $_ } | Select-Object -First 1); if ($s) { & $s }
```

### Q8: Why does PowerShell freeze or pause during guest installation? (The QuickEdit Trap)
**The Trap**: Windows Console has **QuickEdit Mode** enabled by default. If you click anywhere inside the blue PowerShell console window, Windows pauses execution to allow text selection!  
**Symptoms**: The terminal appears stuck on "Installing Python..." or "Configuring Network..." for several minutes.  
**Immediate Fix**: Click inside the PowerShell window and press **`Esc`**, then press **`Enter`**. Output will resume immediately.  
**Permanent Prevention**: Right-click the PowerShell title bar &rarr; **Properties** &rarr; uncheck **QuickEdit Mode** &rarr; click **OK**.

### Q9: Why does the script report "Access is denied" when configuring the network interface?
**Cause**: PowerShell was launched as a standard user.  
**Fix**: Close the console. Click Start &rarr; type `powershell` &rarr; right-click **Windows PowerShell** &rarr; select **Run as Administrator**.

### Q10: The script finished, but Ubuntu still waits at "Awaiting guest agent...". What do I do?
**Fix: Simply restart the Windows VM!**  
In Windows PowerShell:
```powershell
Restart-Computer
```
Or from your Ubuntu host terminal:
```bash
virsh reboot cape-win
```

**Why restarting works immediately**:
1. **Network Binding**: Reboots flush any half-open DHCP sockets and cleanly bind static IP `192.168.250.100` to the host bridge.
2. **Auto-Launch Agent**: `setup-agent.ps1` places `agent.pyw` into `%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup\`. On boot, Windows autologs into user `cape` and launches the agent listening on port 8000.
3. **Instant Snapshot**: Within 10–15 seconds, the orchestrator detects `HTTP 200 OK`, captures the live running snapshot, and launches all CAPEv2 services!

### Q11: How do I access the Windows graphical console from Ubuntu?
- **With Desktop GUI / X11 Forwarding**:
  ```bash
  virt-viewer -c qemu:///system cape-win
  ```
- **Headless Server via VNC**:
  ```bash
  virsh vncdisplay cape-win
  ```
  *(e.g., `:0` connects to port `5900`, `:1` to `5901`). Connect using Remmina, TigerVNC, or RealVNC.*

### Q12: What if Windows pauses asking for a Microsoft Account or internet connection?
If setup stops at "Let's connect you to a network":
1. Press `Shift + F10` to open a command prompt.
2. Type `OOBE\BYPASSNRO` and press Enter. The VM will restart.
3. Select **"I don't have internet"**, then **"Continue with limited setup"**.
4. Set username to `cape` and password to `cape`.

---

## ⚙️ Sandbox Operations & Task Scheduling

### Q13: Why are my submitted malware tasks stuck in 'Pending' on the web dashboard?
**Root Cause**:  
The Web interface (`cape-web.service`) only writes tasks to the database. It does not control VMs.  
Task dispatching and VM orchestration are managed exclusively by **`cape.service`** (`cuckoo.py`), and result processing is handled by **`cape-processor.service`** (`utils/process.py`). If either daemon is stopped or crashed, tasks will remain in `pending` indefinitely!

**Instant Fix**:
```bash
# 1. Enable and start all four microservices:
sudo systemctl enable --now cape-rooter cape cape-processor cape-web

# 2. Or run the self-repair engine:
sudo ./repair.sh

# 3. Or use the master CLI launcher:
cape-start
```

**Verify Service Health**:
```bash
cape-status
```
All four services must show `active (running)`.

### Q14: An analysis task has been running for 4 minutes. Is the VM stuck?
**No.** CAPEv2 dynamic analysis runs for a preconfigured duration (typically 120–300 seconds) to allow malware to sleep, unpack, contact C2 servers, and inject into child processes. After execution completes, the dump analyzer extracts memory dumps, PCAPs, API logs, and dropped files. A typical task takes 3 to 6 minutes total.

### Q15: How do I view live real-time analysis logs while a task runs?
Open a terminal on your Ubuntu host and monitor the master scheduler:
```bash
sudo journalctl -u cape.service -f -n 50
# Or directly view cuckoo.log:
tail -f /opt/CAPEv2/log/cuckoo.log
```
You will see libvirt reverting `cape-win` to `cape-clean`, dispatching the sample to the guest agent, and collecting behavioral results.

---

## 📸 VM Snapshot & State Management

### Q16: Why did CAPEv2 crash with `Snapshot 'cape-clean' is not in a 'running' state`?
**Root Cause**:  
CAPEv2 strictly requires analysis snapshots to be taken of live, running VMs with memory (`<state>running</state>`).  
If a snapshot was created using `--disk-only` or when the VM was shut off, libvirt flags it as `<state>disk-snapshot</state>`. CAPEv2 detects this during boot validation and aborts with `CuckooStartupError` to avoid corrupted VM states.

**Autonomous Solution**:
Run the self-repair script:
```bash
sudo ./repair.sh
```
`repair.sh` boots the VM, verifies the guest agent on port 8000, and takes a genuine running snapshot with live RAM memory.

### Q17: Why did libvirt report `Snapshot 'cape-clean' already exists in one or more devices`?
**Root Cause**:  
When snapshot metadata is deleted via `virsh snapshot-delete --metadata`, the underlying QEMU qcow2 block device header table may still retain the internal snapshot block tag. Running `virsh snapshot-create-as` fails because QEMU sees the tag collision.

**Solution**:
Purge the block device header tag via the QEMU monitor before recreating:
```bash
virsh qemu-monitor-command cape-win --hmp 'delvm cape-clean'
virsh snapshot-create-as cape-win cape-clean "Clean Running Baseline"
```
*(This is handled automatically by `repair.sh` and `enable-nonpe.sh`).*

---

## 📦 Non-PE & File Formats Support

### Q18: Why did my Excel or Word analysis fail with `Unable to find any EXCEL.EXE executable`?
**Cause**: The Windows guest VM does not have Microsoft Office installed. CAPEv2's `xls.py` and `doc.py` packages search for `EXCEL.EXE` and `WINWORD.EXE` to detonate VBA macros.  
**Remedy**: See the dedicated [Non-PE Analysis Guide](NON_PE_GUIDE.md) for automated Microsoft Office Deployment Tool (ODT) and Chocolatey setup.

### Q19: Why did my RAR analysis fail with `Unable to find any WinRAR.exe executable`?
**Cause**: CAPEv2's `rar.py` package and Python's `rarfile` library explicitly expect `WinRAR.exe` at `C:\Program Files\WinRAR\WinRAR.exe` to handle RAR archives.  
**Remedy**: Install WinRAR 64-bit silently inside the VM:
```powershell
choco install -y winrar
```
Then recapture the `cape-clean` snapshot.

### Q20: How do I bulk install all Non-PE software suites automatically?
Run the automated non-pe orchestrator on your Ubuntu host:
```bash
sudo ./enable-nonpe.sh
```
Inside the Windows guest, execute Chocolatey to bulk install all handlers:
```powershell
choco install -y winrar 7zip sumatrapdf javaruntime nodejs-lts autoit vcredist-all
```
For complete details, consult the [Non-PE Analysis Guide](NON_PE_GUIDE.md).

---

## 🛠️ Self-Repair & Maintenance

### Q21: How do I recover after an unexpected host reboot or system crash?
Simply run:
```bash
sudo ./repair.sh
```
The self-repair engine:
1. Purges stale PID lock files (`/opt/CAPEv2/cuckoo.pid`).
2. Audits KVM virtualization modules and libvirt sockets.
3. Restarts the isolated network bridge `virbr-cape`.
4. Starts the full 4-service stack (`cape-rooter`, `cape`, `cape-processor`, `cape-web`) in strict dependency order.

### Q22: What if `cape` fails with `ModuleNotFoundError: No module named 'libvirt'`?
**Root Cause**: Ubuntu installs system Python packages to `/usr/lib/python3/dist-packages/`, but CAPEv2 executes inside `/opt/CAPEv2/.venv`. If `libvirt-python` is missing from the virtualenv, CAPE cannot talk to KVM.  
**Fix**:
```bash
sudo /opt/CAPEv2/.venv/bin/pip install libvirt-python certvalidator asn1crypto mscerts
sudo systemctl restart cape-rooter cape cape-processor cape-web
```
*(Both `./install.sh` and `./repair.sh` apply this fix automatically).*
