"""
Diagnostics engine for CAPEv2 Automated Installer.

Provides structured diagnostic probes for every component:
KVM, libvirt, networking, Python, databases, CAPE services, VMs, guest agent.
Each diagnostic returns structured data with symptoms, evidence, and recommendations.
"""
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

from cape_auto.command import CommandRunner, CommandResult
from cape_auto.state import HealthStatus
from cape_auto.logging_setup import get_logger

logger = get_logger("diagnostics")


@dataclass
class DiagnosticResult:
    """Structured diagnostic result."""
    component: str
    status: str  # HealthStatus value
    severity: str = "low"  # low, medium, high, critical
    symptoms: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    probable_causes: list[str] = field(default_factory=list)
    recommended_repairs: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class DiagnosticsEngine:
    """
    Comprehensive diagnostic engine for all CAPEv2 components.

    Each diagnose_* method probes a specific subsystem and returns
    a structured DiagnosticResult.
    """

    def __init__(self, cmd: CommandRunner, cape_root: str = "/opt/CAPEv2"):
        self._cmd = cmd
        self._cape_root = cape_root

    def diagnose_all(self) -> list[DiagnosticResult]:
        """Run all diagnostic probes."""
        results = []
        probes = [
            self.diagnose_os,
            self.diagnose_cpu,
            self.diagnose_kvm,
            self.diagnose_libvirt,
            self.diagnose_network,
            self.diagnose_python,
            self.diagnose_database,
            self.diagnose_cape_repo,
            self.diagnose_cape_services,
            self.diagnose_vm,
            self.diagnose_guest_agent,
        ]
        for probe in probes:
            try:
                result = probe()
                results.append(result)
            except Exception as e:
                results.append(DiagnosticResult(
                    component=probe.__name__.replace("diagnose_", ""),
                    status=HealthStatus.FAIL.value,
                    severity="high",
                    symptoms=[f"Diagnostic probe crashed: {e}"],
                ))
        return results

    def diagnose_os(self) -> DiagnosticResult:
        """Diagnose OS compatibility."""
        result = DiagnosticResult(component="os", status=HealthStatus.PASS.value)

        # Get OS info
        os_release = self._cmd.run_capture(["cat", "/etc/os-release"])
        uname = self._cmd.run_capture(["uname", "-a"])
        arch = self._cmd.run_capture(["dpkg", "--print-architecture"])

        result.raw_data = {"os_release": os_release, "uname": uname, "arch": arch}

        if "ubuntu" not in os_release.lower():
            result.status = HealthStatus.FAIL.value
            result.severity = "critical"
            result.symptoms.append("Not running Ubuntu")
            result.probable_causes.append("Unsupported operating system")
            return result

        # Check Ubuntu version
        version_id = ""
        for line in os_release.splitlines():
            if line.startswith("VERSION_ID="):
                version_id = line.split("=")[1].strip('"')
                break

        result.raw_data["version_id"] = version_id

        if arch.strip() not in ("amd64", "arm64"):
            result.status = HealthStatus.FAIL.value
            result.severity = "critical"
            result.symptoms.append(f"Unsupported architecture: {arch}")

        supported_versions = ["24.04", "22.04"]
        if version_id not in supported_versions:
            result.status = HealthStatus.WARN.value
            result.severity = "medium"
            result.symptoms.append(f"Ubuntu {version_id} is not a primary target")
            result.recommended_repairs.append("Consider Ubuntu 24.04 LTS for best compatibility")

        return result

    def diagnose_cpu(self) -> DiagnosticResult:
        """Diagnose CPU and virtualization capabilities."""
        result = DiagnosticResult(component="cpu", status=HealthStatus.PASS.value)

        lscpu = self._cmd.run_capture(["lscpu"])
        cpuinfo = self._cmd.run_capture(["cat", "/proc/cpuinfo"])

        result.raw_data = {"lscpu": lscpu}

        # Check virtualization flags
        has_vmx = "vmx" in cpuinfo.lower()
        has_svm = "svm" in cpuinfo.lower()

        if not (has_vmx or has_svm):
            result.status = HealthStatus.FAIL.value
            result.severity = "critical"
            result.symptoms.append("No hardware virtualization support detected")
            result.probable_causes.append("VT-x/AMD-V disabled in BIOS or running inside VM without nested virt")
            result.recommended_repairs.append("Enable Intel VT-x or AMD-V in BIOS/UEFI settings")

        # Check /dev/kvm
        kvm_check = self._cmd.run(["test", "-e", "/dev/kvm"])
        if not kvm_check.success:
            result.status = HealthStatus.FAIL.value
            result.severity = "critical"
            result.symptoms.append("/dev/kvm does not exist")
            result.probable_causes.append("KVM kernel modules not loaded or virtualization disabled")
            result.recommended_repairs.extend([
                "Load KVM modules: modprobe kvm_intel or modprobe kvm_amd",
                "Enable virtualization in BIOS/UEFI",
            ])

        # Check AVX for MongoDB
        if "avx" not in cpuinfo.lower():
            result.evidence.append("CPU does not support AVX - may affect MongoDB 5.0+")

        return result

    def diagnose_kvm(self) -> DiagnosticResult:
        """Diagnose KVM availability and health."""
        result = DiagnosticResult(component="kvm", status=HealthStatus.PASS.value)

        # Check /dev/kvm
        kvm_exists = self._cmd.run(["test", "-e", "/dev/kvm"])
        if not kvm_exists.success:
            result.status = HealthStatus.FAIL.value
            result.severity = "critical"
            result.symptoms.append("/dev/kvm not found")
            result.recommended_repairs.append("Check BIOS virtualization settings")
            return result

        # Check KVM modules
        lsmod = self._cmd.run_capture(["lsmod"])
        has_kvm = "kvm" in lsmod.lower()
        result.raw_data["kvm_module_loaded"] = has_kvm

        # Check qemu
        qemu_check = self._cmd.run(["which", "qemu-system-x86_64"])
        result.raw_data["qemu_installed"] = qemu_check.success
        if not qemu_check.success:
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append("qemu-system-x86_64 not found")
            result.recommended_repairs.append("Install QEMU/KVM packages")

        # Check qemu-img
        qemu_img = self._cmd.run(["which", "qemu-img"])
        result.raw_data["qemu_img_installed"] = qemu_img.success

        return result

    def diagnose_libvirt(self) -> DiagnosticResult:
        """Diagnose libvirt health and configuration."""
        result = DiagnosticResult(component="libvirt", status=HealthStatus.PASS.value)

        # Check virsh
        virsh_check = self._cmd.run(["which", "virsh"])
        if not virsh_check.success:
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append("virsh command not found")
            result.recommended_repairs.append("Install libvirt packages")
            return result

        # Check URI
        uri = self._cmd.run(["virsh", "uri"])
        result.raw_data["uri"] = uri.stdout if uri.success else uri.stderr
        if not uri.success:
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append("Cannot connect to libvirt")
            result.evidence.append(uri.stderr)

            # Diagnose further
            # Check services
            for svc in ["libvirtd", "virtqemud", "virtnetworkd"]:
                svc_status = self._cmd.run(["systemctl", "is-active", f"{svc}.service"])
                result.raw_data[f"{svc}_active"] = svc_status.stdout.strip()
                if svc_status.stdout.strip() == "active":
                    result.evidence.append(f"{svc} is active")

            result.probable_causes.append("Libvirt service not running or socket issue")
            result.recommended_repairs.extend([
                "Restart libvirt: systemctl restart libvirtd or virtqemud",
                "Check group membership: usermod -aG libvirt <user>",
            ])
            return result

        # Check version
        version = self._cmd.run(["virsh", "version"])
        result.raw_data["version"] = version.stdout if version.success else ""

        # Check networks
        nets = self._cmd.run(["virsh", "net-list", "--all"])
        result.raw_data["networks"] = nets.stdout if nets.success else ""

        # Check pools
        pools = self._cmd.run(["virsh", "pool-list", "--all"])
        result.raw_data["pools"] = pools.stdout if pools.success else ""

        # Check VMs
        vms = self._cmd.run(["virsh", "list", "--all"])
        result.raw_data["vms"] = vms.stdout if vms.success else ""

        return result

    def diagnose_network(self) -> DiagnosticResult:
        """Diagnose network topology and CAPE network readiness."""
        result = DiagnosticResult(component="network", status=HealthStatus.PASS.value)

        # Get interfaces
        ip_addr = self._cmd.run_capture(["ip", "-j", "addr", "show"])
        ip_route = self._cmd.run_capture(["ip", "route"])
        result.raw_data["ip_route"] = ip_route

        # Check default route
        if "default" not in ip_route:
            result.status = HealthStatus.WARN.value
            result.symptoms.append("No default route found")

        # Check DNS
        dns_check = self._cmd.run(["resolvectl", "status"], timeout=10)
        result.raw_data["dns"] = dns_check.stdout if dns_check.success else "unavailable"

        # Check for SSH session
        ssh_conn = os.environ.get("SSH_CONNECTION", "")
        result.raw_data["ssh_session"] = bool(ssh_conn)
        if ssh_conn:
            result.evidence.append("Running via SSH - remote-safe mode recommended")

        # Check existing firewall
        for fw in ["ufw", "nft", "iptables", "firewalld"]:
            fw_check = self._cmd.run(["which", fw])
            result.raw_data[f"has_{fw}"] = fw_check.success

        # Check listening ports
        ss = self._cmd.run_capture(["ss", "-lntup"])
        result.raw_data["listening_ports"] = ss

        return result

    def diagnose_python(self) -> DiagnosticResult:
        """Diagnose Python environment for CAPE."""
        result = DiagnosticResult(component="python", status=HealthStatus.PASS.value)

        # System Python
        py_ver = self._cmd.run_capture(["python3", "--version"])
        result.raw_data["system_python"] = py_ver

        # Check CAPE Python env
        cape_poetry = os.path.join(self._cape_root, ".venv")
        cape_has_venv = os.path.isdir(cape_poetry)
        result.raw_data["cape_venv_exists"] = cape_has_venv

        # Check poetry
        poetry_check = self._cmd.run(["which", "poetry"])
        result.raw_data["poetry_installed"] = poetry_check.success

        # Check uv
        uv_check = self._cmd.run(["which", "uv"])
        result.raw_data["uv_installed"] = uv_check.success

        if os.path.isdir(self._cape_root):
            # Try importing CAPE using venv python if available
            venv_python = os.path.join(self._cape_root, ".venv", "bin", "python")
            py_bin = venv_python if os.path.isfile(venv_python) else "python3"
            test_import = self._cmd.run(
                [py_bin, "-c", "import sys; sys.path.insert(0, '.'); import lib.cuckoo.core.startup"],
                cwd=self._cape_root,
                timeout=30,
            )
            if not test_import.success:
                result.status = HealthStatus.WARN.value
                result.symptoms.append("CAPE Python imports may have issues")
                result.evidence.append(test_import.stderr[:500])

        return result

    def diagnose_database(self) -> DiagnosticResult:
        """Diagnose database availability."""
        result = DiagnosticResult(component="database", status=HealthStatus.PASS.value)

        # Check MongoDB
        mongo_active = self._cmd.run(["systemctl", "is-active", "mongod"])
        result.raw_data["mongod_active"] = mongo_active.stdout.strip()

        if mongo_active.stdout.strip() == "active":
            # Test connection
            mongo_test = self._cmd.run(
                ["mongosh", "--eval", "db.runCommand({ping: 1})", "--quiet"],
                timeout=15,
            )
            result.raw_data["mongo_reachable"] = mongo_test.success
            if not mongo_test.success:
                result.status = HealthStatus.WARN.value
                result.symptoms.append("MongoDB service active but connection test failed")
        else:
            # Check if MongoDB is expected
            mongo_installed = self._cmd.run(["which", "mongod"])
            if mongo_installed.success:
                result.status = HealthStatus.WARN.value
                result.symptoms.append("MongoDB installed but not running")
                result.recommended_repairs.append("Start MongoDB: systemctl start mongod")

        # Check PostgreSQL
        pg_active = self._cmd.run(["systemctl", "is-active", "postgresql"])
        result.raw_data["postgresql_active"] = pg_active.stdout.strip()

        return result

    def diagnose_cape_repo(self) -> DiagnosticResult:
        """Diagnose CAPE repository state."""
        result = DiagnosticResult(component="cape_repo", status=HealthStatus.PASS.value)

        if not os.path.isdir(self._cape_root):
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append(f"CAPE directory not found: {self._cape_root}")
            return result

        # Check git
        git_status = self._cmd.run(["git", "status", "--porcelain"], cwd=self._cape_root)
        result.raw_data["is_git_repo"] = git_status.success
        if not git_status.success:
            result.status = HealthStatus.WARN.value
            result.symptoms.append("CAPE directory exists but is not a git repository")
            return result

        # Get commit
        commit = self._cmd.run_capture(["git", "rev-parse", "HEAD"], cwd=self._cape_root)
        result.raw_data["commit"] = commit.strip()

        # Check dirty
        dirty = git_status.stdout.strip()
        result.raw_data["dirty"] = bool(dirty)
        if dirty:
            result.evidence.append("Working tree has uncommitted changes")

        # Get remote
        remote = self._cmd.run_capture(["git", "remote", "get-url", "origin"], cwd=self._cape_root)
        result.raw_data["remote"] = remote.strip()

        # Get branch
        branch = self._cmd.run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self._cape_root)
        result.raw_data["branch"] = branch.strip()

        return result

    def diagnose_cape_services(self) -> DiagnosticResult:
        """Diagnose CAPE systemd services."""
        result = DiagnosticResult(component="cape_services", status=HealthStatus.PASS.value)

        services = ["cape", "cape-processor", "cape-web", "cape-rooter"]
        active_count = 0

        for svc in services:
            svc_name = f"{svc}.service"
            status = self._cmd.run(["systemctl", "is-active", svc_name])
            is_active = status.stdout.strip() == "active"
            result.raw_data[svc] = status.stdout.strip()

            if is_active:
                active_count += 1
            else:
                # Check if service exists
                exists = self._cmd.run(["systemctl", "cat", svc_name])
                if exists.success:
                    result.symptoms.append(f"{svc} exists but is not active")
                    # Get journal
                    journal = self._cmd.run(
                        ["journalctl", "-u", svc_name, "-n", "20", "--no-pager"]
                    )
                    if journal.success:
                        result.evidence.append(f"Journal for {svc}:\n{journal.stdout[-500:]}")

        if active_count == 0 and any(
            self._cmd.run(["systemctl", "cat", f"{s}.service"]).success for s in services
        ):
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append("No CAPE services are running")
        elif active_count < len(services):
            result.status = HealthStatus.WARN.value
            result.severity = "medium"

        return result

    def diagnose_vm(self) -> DiagnosticResult:
        """Diagnose VM state."""
        result = DiagnosticResult(component="vm", status=HealthStatus.PASS.value)

        vms = self._cmd.run(["virsh", "list", "--all"])
        if not vms.success:
            result.status = HealthStatus.FAIL.value
            result.symptoms.append("Cannot list VMs")
            return result

        result.raw_data["vms"] = vms.stdout

        # Check for CAPE VM
        if "cape-win" not in vms.stdout:
            result.status = HealthStatus.WARN.value
            result.symptoms.append("No 'cape-win' VM found")

        # Check snapshots
        snap_check = self._cmd.run(["virsh", "snapshot-list", "cape-win"])
        if snap_check.success:
            result.raw_data["snapshots"] = snap_check.stdout
        else:
            result.raw_data["snapshots"] = "unavailable"

        return result

    def diagnose_guest_agent(self) -> DiagnosticResult:
        """Diagnose guest agent connectivity."""
        result = DiagnosticResult(component="guest_agent", status=HealthStatus.NOT_APPLICABLE.value)

        # Only meaningful if VM exists and is running
        vm_running = self._cmd.run(
            "virsh list --state-running | grep -q cape-win",
            shell=True,
        )
        if not vm_running.success:
            result.evidence.append("VM not running - agent check skipped")
            return result

        result.status = HealthStatus.PASS.value

        # Try HTTP connection to agent
        agent_check = self._cmd.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "5", "http://192.168.250.100:8000"],
            timeout=15,
        )
        if agent_check.success and agent_check.stdout.strip() == "200":
            result.evidence.append("Agent HTTP endpoint responding")
        else:
            result.status = HealthStatus.FAIL.value
            result.severity = "high"
            result.symptoms.append("Cannot reach guest agent")
            result.recommended_repairs.extend([
                "Check VM is running: virsh list",
                "Check guest IP: verify 192.168.250.100 is correct",
                "Check agent is running inside guest",
                "Check Windows firewall allows port 8000",
            ])

        return result

    def generate_report(self, results: list[DiagnosticResult]) -> str:
        """Generate a human-readable diagnostic report."""
        lines = [
            "=" * 60,
            "CAPEv2 Diagnostic Report",
            "=" * 60,
            "",
        ]

        status_symbols = {
            HealthStatus.PASS.value: "[PASS]",
            HealthStatus.WARN.value: "[WARN]",
            HealthStatus.FAIL.value: "[FAIL]",
            HealthStatus.BLOCKED.value: "[BLOCKED]",
            HealthStatus.NOT_APPLICABLE.value: "[- N/A]",
        }

        for r in results:
            symbol = status_symbols.get(r.status, "? UNKNOWN")
            lines.append(f"  {r.component:<20s} {symbol}")

            if r.symptoms:
                for s in r.symptoms:
                    lines.append(f"      Symptom: {s}")
            if r.probable_causes:
                for c in r.probable_causes:
                    lines.append(f"      Cause:   {c}")
            if r.recommended_repairs:
                for rep in r.recommended_repairs:
                    lines.append(f"      Repair:  {rep}")
            if r.symptoms or r.probable_causes:
                lines.append("")

        lines.append("=" * 60)

        # Overall status
        has_fail = any(r.status == HealthStatus.FAIL.value for r in results)
        has_warn = any(r.status == HealthStatus.WARN.value for r in results)
        if has_fail:
            lines.append("Overall: ISSUES DETECTED - see details above")
        elif has_warn:
            lines.append("Overall: WARNINGS - review recommended")
        else:
            lines.append("Overall: ALL CHECKS PASSED")

        return "\n".join(lines)
