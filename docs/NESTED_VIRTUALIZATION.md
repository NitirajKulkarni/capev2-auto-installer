# 💻 Nested Virtualization Setup & Hypervisor Compatibility Guide

When running an Ubuntu CAPEv2 host inside a virtual machine (such as Oracle VirtualBox, VMware Workstation, Proxmox VE, or Hyper-V), **Nested Virtualization** must be enabled so Ubuntu can expose hardware acceleration (`/dev/kvm`) to QEMU/KVM for running Windows sandbox guests.

---

## 📑 Table of Contents

- [Preflight Hardware Checks](#preflight-hardware-checks)
- [Oracle VirtualBox Configuration](#oracle-virtualbox-configuration)
  - [The Windows Host "Green Turtle" (VBS / Hyper-V Trap)](#the-windows-host-green-turtle-vbs--hyper-v-trap)
  - [Automated 1-Click Fix (`enable-windows-virtualization.bat`)](#automated-1-click-fix-enable-windows-virtualizationbat)
- [VMware Workstation & Player](#vmware-workstation--player)
- [VMware ESXi & vSphere](#vmware-esxi--vsphere)
- [Proxmox VE](#proxmox-ve)
- [Microsoft Hyper-V Host](#microsoft-hyper-v-host)
- [KVM / QEMU Host (L1 Hypervisor)](#kvm--qemu-host-l1-hypervisor)
- [Verifying `/dev/kvm` Inside Ubuntu](#verifying-devkvm-inside-ubuntu)

---

## Preflight Hardware Checks

Before configuring your hypervisor, ensure your physical host motherboard has CPU virtualization enabled in BIOS/UEFI:
- **Intel**: "Intel Virtualization Technology" (VT-x) and "Intel VT-d".
- **AMD**: "SVM Mode" (Secure Virtual Machine) or "AMD-V".

---

## Oracle VirtualBox Configuration

### Enabling Nested VT-x/AMD-V in VirtualBox
1. Shut down your Ubuntu virtual machine completely.
2. Open VirtualBox Manager &rarr; select your Ubuntu VM &rarr; click **Settings**.
3. Navigate to **System** &rarr; **Processor** tab.
4. Check the box **"Enable Nested VT-x/AMD-V"**.
5. Click **OK** and start the VM.

*If the checkbox is greyed out:*
Open Command Prompt or PowerShell on your host machine and run:
```cmd
cd "C:\Program Files\Oracle\VirtualBox"
VBoxManage modifyvm "<Name-of-Ubuntu-VM>" --nested-hw-virt on
```

---

### The Windows Host "Green Turtle" (VBS / Hyper-V Trap)

If your physical host runs Windows 10 or Windows 11 and VirtualBox shows a **Green Turtle icon** in the status bar (instead of a blue V), VirtualBox is operating in **Slow Execution Mode (NEM - Native Execution Mode)**.

**Why this breaks CAPEv2**:
Windows Hyper-V, Virtualization-Based Security (VBS), Memory Integrity (HVCI), or WSL2 monopolizes the physical CPU's VT-x extensions. As a result, VirtualBox cannot expose VT-x to the Ubuntu guest, and `/dev/kvm` will NOT be created inside Ubuntu.

---

### Automated 1-Click Fix (`enable-windows-virtualization.bat`)

This repository includes a dedicated Windows remediation script located in the repository root:
[`enable-windows-virtualization.bat`](../enable-windows-virtualization.bat).

1. On your Windows physical host, right-click `enable-windows-virtualization.bat` and select **Run as Administrator**.
2. Choose Option `[1]` to disable Hyper-V, DeviceGuard, and VBS locks while leaving standard virtualization active.
3. Reboot your Windows host machine.
4. Start VirtualBox &rarr; verify the green turtle is gone and replaced by the blue V icon.

---

## VMware Workstation & Player

1. Shut down the Ubuntu virtual machine.
2. In VMware, click **Edit virtual machine settings**.
3. Select **Processors** from the hardware list.
4. Check the box:
   - ✅ **Virtualize Intel VT-x/EPT or AMD-V/RVI**
   - ✅ *(Optional)* **Virtualize CPU performance counters**
5. Click **OK** and power on the VM.

---

## VMware ESXi & vSphere

1. Log into the vSphere Web Client / ESXi Host Client.
2. Power off the Ubuntu VM.
3. Edit VM settings &rarr; expand **CPU**.
4. Check the box: **"Expose hardware assisted virtualization to the guest OS"**.
5. Save settings and power on the VM.

---

## Proxmox VE

Proxmox uses KVM natively. To pass host virtualization extensions through to your Ubuntu VM:

1. Select your Ubuntu VM in the Proxmox web interface.
2. Navigate to **Hardware** &rarr; select **Processor**.
3. Click **Edit** &rarr; set **Type** to **`host`**.
4. Click **OK** and restart the VM.

*Or via Proxmox host shell:*
```bash
qm set <VM_ID> --cpu host
```

---

## Microsoft Hyper-V Host

If your physical host is Windows Server or Windows Pro running Hyper-V:

1. Open **Windows PowerShell as Administrator** on the Windows host.
2. Run:
   ```powershell
   Set-VMProcessor -VMName "<Your-Ubuntu-VM-Name>" -ExposeVirtualizationExtensions $true
   ```
3. Restart the Ubuntu virtual machine.

---

## KVM / QEMU Host (L1 Hypervisor)

If your Ubuntu host runs as a KVM guest on top of a Linux bare-metal server:

1. Verify nested virtualization is enabled on the bare-metal Linux host:
   ```bash
   # For Intel:
   cat /sys/module/kvm_intel/parameters/nested
   # (Should output 'Y' or '1')
   
   # For AMD:
   cat /sys/module/kvm_amd/parameters/nested
   # (Should output '1')
   ```
2. In your libvirt XML definition for the Ubuntu VM, set the CPU mode to `host-passthrough`:
   ```xml
   <cpu mode='host-passthrough' check='none'/>
   ```

---

## Verifying `/dev/kvm` Inside Ubuntu

Once your hypervisor is properly configured, boot into Ubuntu and run these verification commands:

```bash
# 1. Check for hardware virtualization flags
egrep -c '(vmx|svm)' /proc/cpuinfo
# (Must output a number greater than 0)

# 2. Check if /dev/kvm exists
ls -l /dev/kvm
# (Output should show: crw-rw----+ 1 root kvm ... /dev/kvm)

# 3. Use kvm-ok diagnostic
sudo kvm-ok
# Expected output:
# INFO: /dev/kvm exists
# KVM acceleration can be used
```

If `kvm-ok` outputs `KVM acceleration can be used`, your environment is 100% ready for automated CAPEv2 deployment!
