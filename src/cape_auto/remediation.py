"""
Remediation engine for CAPEv2 Automated Installer.

Provides structured repair strategies for common failures.
Each remediation has risk level, prerequisites, commands, verification, and rollback.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from cape_auto.command import CommandRunner
from cape_auto.state import StateManager, ResourceOwnership
from cape_auto.logging_setup import get_logger

logger = get_logger("remediation")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass
class Remediation:
    """A structured repair action."""
    remediation_id: str
    target_component: str
    description: str
    risk_level: str = RiskLevel.LOW.value
    prerequisites: list[str] = field(default_factory=list)
    verification_cmd: Optional[str] = None
    rollback_steps: list[str] = field(default_factory=list)


class RemediationEngine:
    """
    Automatic remediation engine with risk-aware repair selection.

    Default automation policy:
        LOW        = automatic
        MEDIUM     = automatic if configured
        HIGH       = do not execute remotely
        DESTRUCTIVE = never automatic unless explicit flag
    """

    def __init__(
        self,
        cmd: CommandRunner,
        state: StateManager,
        allow_medium: bool = True,
        allow_high: bool = False,
        allow_destructive: bool = False,
        is_remote: bool = False,
    ):
        self._cmd = cmd
        self._state = state
        self._allow_medium = allow_medium
        self._allow_high = allow_high and not is_remote
        self._allow_destructive = allow_destructive
        self._is_remote = is_remote

    def can_auto_execute(self, risk: str) -> bool:
        """Check if a remediation can be automatically executed."""
        if risk == RiskLevel.LOW.value:
            return True
        if risk == RiskLevel.MEDIUM.value:
            return self._allow_medium
        if risk == RiskLevel.HIGH.value:
            return self._allow_high
        if risk == RiskLevel.DESTRUCTIVE.value:
            return self._allow_destructive
        return False

    def repair_service(self, service_name: str) -> bool:
        """Repair a failed systemd service."""
        logger.info(f"Attempting repair of service: {service_name}")

        # Step 1: Check status
        status = self._cmd.run(["systemctl", "status", f"{service_name}.service"])
        logger.debug(f"Service status: {status.stdout}")

        # Step 2: Check if it exists
        exists = self._cmd.run(["systemctl", "cat", f"{service_name}.service"])
        if not exists.success:
            logger.error(f"Service {service_name} does not exist")
            return False

        # Step 3: Reload daemon in case unit changed
        self._cmd.run(["systemctl", "daemon-reload"])

        # Step 4: Try restart
        restart = self._cmd.run(["systemctl", "restart", f"{service_name}.service"], timeout=30)
        if restart.success:
            # Verify
            import time
            time.sleep(2)
            check = self._cmd.run(["systemctl", "is-active", f"{service_name}.service"])
            if check.stdout.strip() == "active":
                logger.info(f"Service {service_name} repaired successfully")
                return True

        # Step 5: Check journal for clues
        journal = self._cmd.run(
            ["journalctl", "-u", f"{service_name}.service", "-n", "50", "--no-pager"]
        )
        logger.debug(f"Journal output:\n{journal.stdout}")

        # Classify failure
        stderr_combined = (status.stderr + "\n" + journal.stdout).lower()

        if "modulenotfounderror" in stderr_combined or "importerror" in stderr_combined:
            logger.info("Detected Python import error - attempting environment repair")
            return self.repair_python_env()

        if "address already in use" in stderr_combined or "port" in stderr_combined:
            logger.info("Detected port conflict")
            return self._handle_port_conflict(service_name, stderr_combined)

        if "permission denied" in stderr_combined:
            logger.info("Detected permission issue")
            return self.repair_cape_permissions()

        logger.warning(f"Could not automatically repair {service_name}")
        return False

    def repair_libvirt(self) -> bool:
        """Repair libvirt connectivity."""
        logger.info("Attempting libvirt repair")

        # Discover which daemon to use
        for daemon in ["virtqemud", "libvirtd"]:
            check = self._cmd.run(["systemctl", "cat", f"{daemon}.service"])
            if check.success:
                # Enable and start
                self._cmd.run(["systemctl", "enable", f"{daemon}.service"])
                self._cmd.run(["systemctl", "enable", f"{daemon}.socket"])
                self._cmd.run(["systemctl", "start", f"{daemon}.socket"])
                self._cmd.run(["systemctl", "start", f"{daemon}.service"])

        # Also try network daemons
        for daemon in ["virtnetworkd", "virtstoraged", "virtlogd"]:
            check = self._cmd.run(["systemctl", "cat", f"{daemon}.service"])
            if check.success:
                self._cmd.run(["systemctl", "enable", f"{daemon}.service"])
                self._cmd.run(["systemctl", "start", f"{daemon}.service"])

        # Verify
        uri = self._cmd.run(["virsh", "uri"])
        if uri.success:
            logger.info("Libvirt connection restored")
            return True

        logger.warning("Libvirt repair failed")
        return False

    def repair_libvirt_network(self, network_name: str) -> bool:
        """Repair a CAPE-owned libvirt network."""
        if not self._state.is_owned_by_us("libvirt_network", network_name):
            logger.warning(f"Network {network_name} is not owned by this installer - skipping")
            return False

        logger.info(f"Repairing libvirt network: {network_name}")

        # Try to start it
        start = self._cmd.run(["virsh", "net-start", network_name])
        if start.success:
            self._cmd.run(["virsh", "net-autostart", network_name])
            logger.info(f"Network {network_name} started")
            return True

        # If it doesn't exist, we need to redefine it
        logger.warning(f"Network {network_name} could not be started")
        return False

    def repair_python_env(self, cape_root: str = "/opt/CAPEv2") -> bool:
        """Repair CAPE Python environment."""
        import os
        logger.info("Attempting Python environment repair")

        if not os.path.isdir(cape_root):
            logger.error(f"CAPE root not found: {cape_root}")
            return False

        # Detect package manager
        uv_check = self._cmd.run(["which", "uv"])
        uv_bin = "uv" if uv_check.success else ("/usr/local/bin/uv" if os.path.isfile("/usr/local/bin/uv") else None)
        poetry_path = "/etc/poetry/bin/poetry"
        poetry_bin = poetry_path if os.path.isfile(poetry_path) else ("poetry" if self._cmd.run(["which", "poetry"]).success else None)

        if uv_bin:
            logger.info("Using uv for environment repair (pinning Python 3.12 for python-flirt / django)")
            self._cmd.run([uv_bin, "python", "install", "3.12"], timeout=300)
            venv_path = os.path.join(cape_root, ".venv")
            self._cmd.run([uv_bin, "venv", "--python", "3.12", venv_path], cwd=cape_root, timeout=120)
            result = self._cmd.run(
                [uv_bin, "sync", "--python", "3.12", "--no-install-project"],
                cwd=cape_root,
                timeout=600,
            )
        elif poetry_bin:
            logger.info("Using poetry for environment repair")
            py_exec = "python3.12" if self._cmd.run(["which", "python3.12"]).success else "python3.11"
            self._cmd.run([poetry_bin, "env", "use", py_exec], cwd=cape_root, timeout=60)
            result = self._cmd.run(
                [poetry_bin, "install"],
                cwd=cape_root,
                timeout=600,
            )
        else:
            logger.error("Neither poetry nor uv found - cannot repair Python env")
            return False

        if result.success:
            venv_py = os.path.join(cape_root, ".venv", "bin", "python")
            if os.path.isfile(venv_py):
                v_check = self._cmd.run([venv_py, "-c", "import django; import flirt; print('OK')"], timeout=30)
                if not v_check.success:
                    logger.warning("Dependencies missing after repair: django or flirt import failed")
                    return False
            logger.info("Python environment repaired and verified successfully")
            return True

        logger.warning(f"Python environment repair failed: {result.stderr[:200]}")
        return False

    def repair_cape_permissions(self, cape_root: str = "/opt/CAPEv2",
                                cape_user: str = "cape") -> bool:
        """Fix CAPE directory ownership."""
        logger.info(f"Fixing ownership of {cape_root} to {cape_user}")
        result = self._cmd.run(
            ["chown", "-R", f"{cape_user}:{cape_user}", cape_root],
            timeout=120,
        )
        return result.success

    def repair_kvm_modules(self) -> bool:
        """Attempt to load KVM kernel modules."""
        logger.info("Attempting to load KVM modules")

        # Try Intel
        intel = self._cmd.run(["modprobe", "kvm_intel"])
        if intel.success:
            logger.info("Loaded kvm_intel module")
            return True

        # Try AMD
        amd = self._cmd.run(["modprobe", "kvm_amd"])
        if amd.success:
            logger.info("Loaded kvm_amd module")
            return True

        # Check if nested virt
        nested = self._cmd.run(["cat", "/sys/module/kvm_intel/parameters/nested"])
        if not nested.success:
            nested = self._cmd.run(["cat", "/sys/module/kvm_amd/parameters/nested"])

        logger.warning("Failed to load KVM modules - may need BIOS configuration")
        return False

    def repair_package_manager(self) -> bool:
        """Repair broken apt/dpkg state."""
        logger.info("Attempting package manager repair")

        # Check for dpkg locks
        lock_check = self._cmd.run(["fuser", "/var/lib/dpkg/lock-frontend"])
        if lock_check.success and lock_check.stdout.strip():
            logger.warning(f"dpkg lock held by PID: {lock_check.stdout.strip()}")
            logger.info("Waiting for lock release...")
            import time
            time.sleep(30)

        # dpkg --configure -a
        configure = self._cmd.run(["dpkg", "--configure", "-a"], timeout=120)

        # apt-get -f install
        fix = self._cmd.run(["apt-get", "-f", "install", "-y"], timeout=300)

        # apt-get update
        update = self._cmd.run(["apt-get", "update"], timeout=120)

        return update.success

    def repair_database(self, db_type: str = "mongodb") -> bool:
        """Repair database service."""
        logger.info(f"Attempting {db_type} repair")

        if db_type == "mongodb":
            service_name = "mongod"
        elif db_type == "postgresql":
            service_name = "postgresql"
        else:
            return False

        return self.repair_service(service_name)

    def _handle_port_conflict(self, service_name: str, error_text: str) -> bool:
        """Handle port conflict for a service."""
        # Find which port is conflicting
        ss = self._cmd.run(["ss", "-lntup"])
        logger.info(f"Current listening ports:\n{ss.stdout}")

        # We cannot automatically kill unrelated processes
        logger.warning("Port conflict detected - manual resolution may be needed")
        return False

    def get_repair_for_error(self, error_category: str) -> list[Remediation]:
        """Get applicable remediations for an error category."""
        repairs = {
            "PACKAGE_ERROR": [
                Remediation(
                    remediation_id="repair_apt",
                    target_component="packages",
                    description="Repair package manager state",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "SERVICE_ERROR": [
                Remediation(
                    remediation_id="restart_service",
                    target_component="systemd",
                    description="Restart failed service",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "LIBVIRT_ERROR": [
                Remediation(
                    remediation_id="repair_libvirt",
                    target_component="libvirt",
                    description="Restart libvirt daemons",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "PYTHON_ERROR": [
                Remediation(
                    remediation_id="repair_python",
                    target_component="python",
                    description="Reinstall Python dependencies",
                    risk_level=RiskLevel.MEDIUM.value,
                )
            ],
            "PERMISSION_ERROR": [
                Remediation(
                    remediation_id="fix_permissions",
                    target_component="filesystem",
                    description="Fix CAPE directory ownership",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "KVM_ERROR": [
                Remediation(
                    remediation_id="load_kvm",
                    target_component="kvm",
                    description="Load KVM kernel modules",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "DATABASE_ERROR": [
                Remediation(
                    remediation_id="repair_database",
                    target_component="database",
                    description="Restart database service",
                    risk_level=RiskLevel.LOW.value,
                )
            ],
            "NETWORK_ERROR": [
                Remediation(
                    remediation_id="repair_network",
                    target_component="network",
                    description="Repair CAPE analysis network",
                    risk_level=RiskLevel.MEDIUM.value,
                )
            ],
        }
        return repairs.get(error_category, [])

    def classify_error(self, stderr: str, exit_code: int) -> str:
        """Classify an error into a category based on stderr content."""
        stderr_lower = stderr.lower()

        if any(w in stderr_lower for w in ["dpkg", "apt", "package", "unmet dependencies"]):
            return "PACKAGE_ERROR"
        if any(w in stderr_lower for w in ["dns", "resolve", "name resolution"]):
            return "DNS_ERROR"
        if any(w in stderr_lower for w in ["permission denied", "access denied"]):
            return "PERMISSION_ERROR"
        if any(w in stderr_lower for w in ["systemctl", "service", "unit"]):
            return "SERVICE_ERROR"
        if any(w in stderr_lower for w in ["modulenotfounderror", "importerror", "pip", "poetry"]):
            return "PYTHON_ERROR"
        if any(w in stderr_lower for w in ["libvirt", "virsh", "qemu"]):
            return "LIBVIRT_ERROR"
        if any(w in stderr_lower for w in ["kvm", "/dev/kvm"]):
            return "KVM_ERROR"
        if any(w in stderr_lower for w in ["mongod", "postgresql", "database"]):
            return "DATABASE_ERROR"
        if any(w in stderr_lower for w in ["connection refused", "network", "timeout"]):
            return "NETWORK_ERROR"
        if any(w in stderr_lower for w in ["compiler", "gcc", "make"]):
            return "COMPILER_ERROR"
        if exit_code == 126:
            return "PERMISSION_ERROR"
        if exit_code == 127:
            return "PACKAGE_ERROR"

        return "UNKNOWN_ERROR"
