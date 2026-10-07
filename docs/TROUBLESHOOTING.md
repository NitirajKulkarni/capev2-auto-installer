# CAPEv2 Automated Installer - Troubleshooting Guide

This guide covers common issues encountered during CAPEv2 installation and how the automated installer detects, diagnoses, and repairs them.

---

## 1. Hardware Virtualization Issues (`/dev/kvm` Missing)

### Symptom
- Preflight or KVM stage reports: `No hardware virtualization support detected` or `/dev/kvm does not exist`.

### Root Cause
- VT-x (Intel) or AMD-V (AMD) is disabled in the physical host's BIOS/UEFI.
- Or running inside a virtual machine (VMware, VirtualBox, Proxmox, AWS, Azure) without **Nested Virtualization** enabled.

### Automated Remediation
The installer checks whether modules can be loaded:
```bash
sudo modprobe kvm
sudo modprobe kvm_intel # or kvm_amd
```

### Manual Action Required
If the CPU does not expose VT-x/AMD-V instructions:
1. Physical machine: Enter BIOS/UEFI during boot and enable "Intel Virtualization Technology" or "AMD SVM".
2. Nested VM:
   - Proxmox: Set VM CPU type to `host`.
   - VMware ESXi: Enable "Expose hardware assisted virtualization to guest OS".
   - KVM / Libvirt: `<cpu mode='host-passthrough'/>`.

---

## 2. Package Manager Lock (`/var/lib/dpkg/lock-frontend`)

### Symptom
- APT or DPKG commands fail with: `Could not get lock /var/lib/dpkg/lock-frontend`.

### Automated Remediation
The installer automatically:
1. Detects `fuser` locks on `/var/lib/dpkg/lock-frontend`.
2. Waits up to 30 seconds for background unattended-upgrades or apt processes to finish.
3. Automatically runs `dpkg --configure -a` and `apt-get -f install -y`.

---

## 3. Libvirt Socket / Daemon Issues

### Symptom
- `error: failed to connect to the hypervisor` or `error: Cannot recv data: Connection reset by peer`.

### Automated Remediation
On Ubuntu 24.04 and 22.04, libvirt can run in modular or monolithic daemon modes.
The remediation engine automatically:
1. Inspects `virtqemud.service`, `virtnetworkd.service`, and `libvirtd.service`.
2. Reloads systemd daemon definitions: `systemctl daemon-reload`.
3. Restarts active libvirt services and verifies socket accessibility.
4. Ensures `cape` user is in `libvirt` and `kvm` groups:
   ```bash
   sudo usermod -aG libvirt,kvm cape
   ```

---

## 4. Network Subnet Collision

### Symptom
- `virsh net-start cape-analysis` fails with address conflict error.

### Automated Remediation
The installer checks existing host network routes and interfaces before creating `virbr-cape`.
If `192.168.250.0/24` collides with an existing physical or VPN subnet:
- Edit `config.toml`:
  ```toml
  [network]
  subnet = "192.168.251.0/24"
  gateway = "192.168.251.1"
  vm_ip_start = "192.168.251.100"
  ```
- Resume the installation:
  ```bash
  sudo ./install.sh --resume
  ```

---

## 5. MongoDB Installation / AVX Support

### Symptom
- MongoDB fails to start (`Illegal instruction (core dumped)`).

### Root Cause
- MongoDB 5.0+ requires AVX CPU instructions. Some legacy CPUs or VMs with restricted CPU models lack AVX.

### Resolution
- The preflight check flags missing AVX instructions.
- If AVX is unavailable, switch `database.backend` in `config.toml` to `postgresql`:
  ```toml
  [database]
  backend = "postgresql"
  ```
- Re-run: `sudo ./install.sh --resume`.

---

## 6. Windows Guest Provisioning & ISO Path

### Symptom
- Installation finishes with: `PARTIAL SUCCESS: Windows guest provisioning skipped`.

### Root Cause
- `config.toml` has `guest.iso_path = ""`.
- The core CAPEv2 services (CAPE, Web interface, MongoDB, rooter) are fully installed and active, but the Windows VM was not created because no Windows installer ISO was supplied.

### Resolution
1. Download a Windows 10 or 11 ISO.
2. Edit `config.toml`:
   ```toml
   [guest]
   enabled = true
   iso_path = "/path/to/windows10.iso"
   ```
3. Resume to build the VM and take the clean snapshot:
   ```bash
   sudo ./install.sh --from-stage VM_CREATE
   ```
