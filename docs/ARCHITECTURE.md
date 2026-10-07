# CAPEv2 Automated Installer Architecture

## 1. Architectural Philosophy

The CAPEv2 Automated Installer is engineered to treat host environments as dynamic, heterogeneous, and partially configured systems rather than sterile test containers. It enforces four primary tenets:

1. **Preflight Before Action**: Understand the host kernel, architecture, packaging system, and networking topology before touching any files.
2. **Deterministic Checkpointing**: Every stage saves atomic checkpoints so failures can be resumed precisely without side-effects.
3. **Autonomous Root-Cause Remediation**: Failure triggers structured diagnosis, classification into known failure modes, safe execution of risk-tiered fixes, and verification.
4. **Ownership Segregation**: Only resources explicitly tracked in the `ResourceOwnership` registry as `CREATED_BY_INSTALLER` or `MODIFIED_BY_INSTALLER` are managed or removed. Existing user VMs, networks, databases, and services are preserved.

---

## 2. Core Modules

### 2.1 State Management (`state.py`)
- **`StateManager`**: Persists state to `state/state.json` and manifests to `state/manifest.json`.
- **`StageState`**: Captures status (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `SKIPPED`, `BLOCKED`), attempt counts, timestamps, error messages, and attempted remediation IDs.
- **`ResourceRegistry`**: Tracks resource type (`systemd_unit`, `libvirt_network`, `libvirt_domain`, `file`, `user`, `group`), name, and ownership level (`PRE_EXISTING`, `CREATED_BY_INSTALLER`, `MODIFIED_BY_INSTALLER`).

### 2.2 Command Execution (`command.py`)
- **`CommandRunner`**:
  - Full execution tracking (stdout, stderr, exit code, duration).
  - Configurable timeouts with guaranteed cleanup on expiration.
  - Automatic secret redaction for passwords, tokens, and sensitive parameters.
  - Non-interactive environment injection (`DEBIAN_FRONTEND=noninteractive`).
  - User privilege switching (`run_as_user` using `sudo -u`).
  - Dry-run virtualization support.

### 2.3 Diagnostics Engine (`diagnostics.py`)
Probes all functional subsystems and returns structured `DiagnosticResult` objects:
- `diagnose_os`: Ubuntu version, codename, architecture.
- `diagnose_cpu`: Hardware virtualization flags (`vmx`/`svm`), `/dev/kvm`, AVX support.
- `diagnose_kvm`: KVM kernel modules (`kvm_intel`/`kvm_amd`), QEMU binaries.
- `diagnose_libvirt`: Daemon connectivity, active sockets, default pools.
- `diagnose_network`: Interfaces, default gateway, analysis bridge collision checks.
- `diagnose_python`: System Python, virtual environment, dependency imports.
- `diagnose_database`: MongoDB / PostgreSQL daemon health and port bindings.
- `diagnose_cape_repo`: Git repository status, branch, commit consistency.
- `diagnose_cape_services`: Systemd unit states for `cape`, `cape-web`, `cape-processor`, `cape-rooter`.
- `diagnose_vm`: Analysis VM state, libvirt domain existence.
- `diagnose_guest_agent`: Guest agent HTTP endpoint responsiveness.

### 2.4 Remediation Engine (`remediation.py`)
Categorizes errors and executes risk-tiered repairs:
- **Risk Levels**:
  - `LOW`: Safe to execute automatically (e.g., reloading systemd, starting service, cleaning package cache).
  - `MEDIUM`: Automatic if enabled in configuration (e.g., recreating analysis bridge, reinstalling python dependencies).
  - `HIGH`: Requires local confirmation; strictly disabled in remote SSH sessions to prevent disconnection.
  - `DESTRUCTIVE`: Disabled by default; requires explicit configuration flag.
- **Error Classifier**: Maps process exits and stderr messages to specific categories (`PACKAGE_ERROR`, `SERVICE_ERROR`, `LIBVIRT_ERROR`, `PYTHON_ERROR`, `PERMISSION_ERROR`, `KVM_ERROR`, `DATABASE_ERROR`, `NETWORK_ERROR`).

### 2.5 Orchestrator (`orchestrator.py`)
Drives the 25 distinct installation stages:
1. `PREFLIGHT`
2. `BACKUP`
3. `REPOSITORIES`
4. `BASE_PACKAGES`
5. `KVM`
6. `LIBVIRT`
7. `REBOOT_CHECK`
8. `CAPE_REPOSITORY`
9. `CAPE_DEPENDENCIES`
10. `CAPE_INSTALL`
11. `CAPE_CONFIG`
12. `DATABASE`
13. `SYSTEMD`
14. `NETWORK`
15. `VM_CREATE`
16. `VM_INSTALL`
17. `VM_CONFIG`
18. `AGENT`
19. `SNAPSHOT`
20. `MACHINERY_CONFIG`
21. `CAPE_START`
22. `HEALTH_CHECK`
23. `END_TO_END_TEST`
24. `FINALIZE`

---

## 3. Remote Session Protection

When `SSH_CONNECTION` or `SSH_CLIENT` is present in the environment:
1. `_is_remote` mode is activated.
2. High-risk network reconfigurations that could disconnect the management interface are prohibited.
3. Automated reboot requests are inhibited, returning exit code `42` so the user can reboot deliberately.
4. Firewall updates always preserve the incoming SSH port before applying rules.
