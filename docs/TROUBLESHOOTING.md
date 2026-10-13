# 🩺 Comprehensive Troubleshooting & Remediation Guide

This guide details diagnostics, root cause analyses, and automated remedies for common issues encountered across the host, hypervisor, virtual network, and guest sandbox stack.

---

## 📑 Table of Contents

- [1. VM Snapshot & State Failures](#1-vm-snapshot--state-failures)
  - [Symptom A: `Snapshot 'cape-clean' is not in a 'running' state (current state: 'disk-snapshot')`](#symptom-a-snapshot-cape-clean-is-not-in-a-running-state-current-state-disk-snapshot)
  - [Symptom B: `Snapshot 'cape-clean' already exists in one or more devices`](#symptom-b-snapshot-cape-clean-already-exists-in-one-or-more-devices)
- [2. Task Scheduling & Queue Failures](#2-task-scheduling--queue-failures)
  - [Symptom: Submitted tasks remain stuck in 'Pending' forever](#symptom-submitted-tasks-remain-stuck-in-pending-forever)
- [3. In-Guest Package Execution Errors](#3-in-guest-package-execution-errors)
  - [Symptom A: `CuckooPackageError: Unable to find any EXCEL.EXE executable`](#symptom-a-cuckoopackageerror-unable-to-find-any-excelexe-executable)
  - [Symptom B: `CuckooPackageError: Unable to find any WinRAR.exe executable`](#symptom-b-cuckoopackageerror-unable-to-find-any-winrarexe-executable)
- [4. Guest Provisioning & Console Traps](#4-guest-provisioning--console-traps)
  - [Symptom A: PowerShell freezes during script execution (The QuickEdit Trap)](#symptom-a-powershell-freezes-during-script-execution-the-quickedit-trap)
  - [Symptom B: `PSSecurityException: UnauthorizedAccess` in guest](#symptom-b-pssecurityexception-unauthorizedaccess-in-guest)
- [5. Host Virtualization & KVM Failures](#5-host-virtualization--kvm-failures)
  - [Symptom: `/dev/kvm does not exist` or nested virtualization missing](#symptom-devkvm-does-not-exist-or-nested-virtualization-missing)
- [6. Python Environment & Library Bindings](#6-python-environment--library-bindings)
  - [Symptom: `ModuleNotFoundError: No module named 'libvirt'`](#symptom-modulenotfounderror-no-module-named-libvirt)
- [7. Host Package & Lock Contention](#7-host-package--lock-contention)
  - [Symptom: `Could not get lock /var/lib/dpkg/lock-frontend`](#symptom-could-not-get-lock-varlibdpkglock-frontend)

---

## 1. VM Snapshot & State Failures

### Symptom A: `Snapshot 'cape-clean' is not in a 'running' state (current state: 'disk-snapshot')`

#### Root Cause
CAPEv2 dynamic analysis requires reverting directly into live RAM memory so the VM is immediately operational and listening on port 8000 without undergoing a full OS reboot cycle.  
If a snapshot was created using `--disk-only` or when the VM was shut down, libvirt flags the snapshot metadata with `<state>disk-snapshot</state>` or `<state>shutoff</state>`. When `cape.service` boots, its preflight check validates that `<state>` equals `running`. Finding anything else triggers `CuckooStartupError` and terminates the daemon.

#### Automated Solution
Run the self-repair script on the Ubuntu host:
```bash
sudo ./repair.sh
```
`repair.sh` automatically:
1. Stops competing daemons (`cape.service`, `cape-processor.service`) to release VM locks.
2. Boots `cape-win` and polls until the guest agent on port 8000 responds with `HTTP 200 OK`.
3. Purges invalid snapshot references.
4. Captures a live snapshot with live RAM state (`<state>running</state>`).
5. Restarts the full service stack.

---

### Symptom B: `Snapshot 'cape-clean' already exists in one or more devices`

#### Root Cause
When a snapshot metadata entry is deleted using `virsh snapshot-delete cape-win cape-clean --metadata`, libvirt deletes its XML metadata file from `/var/lib/libvirt/qemu/snapshot/cape-win/`, but **does not purge the internal snapshot tag from the underlying QEMU qcow2 block device header**.  
When `virsh snapshot-create-as` is called later, QEMU checks the disk block header, finds the duplicate tag `cape-clean`, and aborts.

#### Solution
Purge the block device header tag directly via the QEMU Monitor (HMP) before recreating:
```bash
# 1. Purge block device header entry
virsh qemu-monitor-command cape-win --hmp 'delvm cape-clean'

# 2. Re-create live snapshot
virsh snapshot-create-as cape-win cape-clean "Clean Running Baseline"
```

---

## 2. Task Scheduling & Queue Failures

### Symptom: Submitted tasks remain stuck in 'Pending' forever

#### Root Cause
The CAPEv2 Web UI (`cape-web.service`) only inserts task rows into the database. It does not communicate with KVM or dispatch jobs.  
Task dispatching and VM state reverting are managed by **`cape.service`** (`cuckoo.py`), while analysis extraction is performed by **`cape-processor.service`** (`utils/process.py`). If either daemon is crashed, disabled, or locked by a stale PID file (`/opt/CAPEv2/cuckoo.pid`), tasks will sit in `pending` indefinitely.

#### Solution
1. Ensure all 4 microservices are active:
   ```bash
   sudo systemctl enable --now cape-rooter cape cape-processor cape-web
   ```
2. Check service status:
   ```bash
   cape-status
   ```
3. Watch the master scheduler claim the pending task:
   ```bash
   sudo journalctl -u cape.service -f -n 30
   ```
   You will see KVM revert `cape-win` to `cape-clean`, dispatch the sample to the guest agent, and transition the task on the dashboard to `running` &rarr; `completed`.

---

## 3. In-Guest Package Execution Errors

### Symptom A: `CuckooPackageError: Unable to find any EXCEL.EXE executable`

#### Root Cause
The in-guest package `modules/packages/xls.py` executes `self.get_path_glob("EXCEL.EXE")`. Because Microsoft Excel is not installed inside the Windows sandbox, the package cannot spawn the process.

#### Solution
Install Microsoft Office inside the VM using the official Microsoft Office Deployment Tool (ODT) or staging an Office installer, and disable Macro / Protected View restrictions.  
*(See the [Non-PE Analysis Guide](NON_PE_GUIDE.md) for automated configuration scripts).*

---

### Symptom B: `CuckooPackageError: Unable to find any WinRAR.exe executable`

#### Root Cause
CAPEv2's `rar.py` and `archive.py` packages explicitly verify the presence of `WinRAR.exe` at `C:\Program Files\WinRAR\WinRAR.exe`. Python's `rarfile` library also depends on `WinRAR.exe` or `unrar.exe`. Even if 7-Zip is installed, `.rar` files fail without WinRAR.

#### Solution
Inside the Windows guest Administrator PowerShell:
```powershell
choco install -y winrar
```
Then recapture the `cape-clean` snapshot.

---

## 4. Guest Provisioning & Console Traps

### Symptom A: PowerShell freezes during script execution (The QuickEdit Trap)

#### Root Cause
Windows Console has **QuickEdit Mode** enabled by default. Clicking inside the blue console window pauses the PowerShell process to allow text selection.

#### Solution
Click inside the PowerShell window and press **`Esc`**, then **`Enter`**. Output will immediately resume scrolling.  
To disable QuickEdit permanently: right-click title bar &rarr; **Properties** &rarr; uncheck **QuickEdit Mode** &rarr; **OK**.

---

### Symptom B: `PSSecurityException: UnauthorizedAccess` in guest

#### Root Cause
Windows PowerShell defaults to `Restricted` execution policy.

#### Solution
Execute with `-ExecutionPolicy Bypass`:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-agent.ps1
```

---

## 5. Host Virtualization & KVM Failures

### Symptom: `/dev/kvm does not exist` or nested virtualization missing

#### Root Cause
- VT-x/AMD-V is disabled in physical host BIOS/UEFI.
- Or running inside a virtual machine (VirtualBox, VMware) without nested virtualization enabled.
- On Windows hosts running VirtualBox, Windows Hyper-V or VBS locks the CPU (indicated by a green turtle icon).

#### Solution
1. On Windows physical hosts: run [`enable-windows-virtualization.bat`](../enable-windows-virtualization.bat) as Administrator.
2. In hypervisors: consult the [Nested Virtualization Guide](NESTED_VIRTUALIZATION.md).

---

## 6. Python Environment & Library Bindings

### Symptom: `ModuleNotFoundError: No module named 'libvirt'`

#### Root Cause
Ubuntu places system packages in `/usr/lib/python3/dist-packages/`, but CAPEv2 runs inside an isolated virtual environment (`/opt/CAPEv2/.venv`). If `libvirt-python` is not compiled into the venv, CAPEv2 cannot issue commands to KVM.

#### Solution
Compile native bindings directly into the virtual environment:
```bash
sudo apt-get install -y pkg-config libvirt-dev python3-libvirt
sudo /opt/CAPEv2/.venv/bin/pip install libvirt-python certvalidator asn1crypto mscerts
sudo systemctl restart cape-rooter cape cape-processor cape-web
```
*(Both `./install.sh` and `./repair.sh` handle this automatically).*

---

## 7. Host Package & Lock Contention

### Symptom: `Could not get lock /var/lib/dpkg/lock-frontend`

#### Root Cause
Ubuntu background processes (`unattended-upgrades`, `apt-daily`) hold the package manager lock.

#### Automated Solution
The installer waits up to 30 seconds for background locks to clear, or safely terminates stale processes and runs `dpkg --configure -a`.
