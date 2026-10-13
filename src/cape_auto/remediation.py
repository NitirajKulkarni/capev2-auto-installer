"""
Remediation engine for CAPEv2 Automated Installer.

Provides structured repair strategies for common failures.
Each remediation has risk level, prerequisites, commands, verification, and rollback.
"""
from dataclasses import dataclass, field
from enum import Enum
import os
import sys
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

        cape_root = "/opt/CAPEv2"
        venv_py = os.path.join(cape_root, ".venv", "bin", "python")
        py_bin = venv_py if os.path.isfile(venv_py) else "/usr/bin/python3"

        if "modulenotfounderror" in stderr_combined or "importerror" in stderr_combined:
            # Check if this is an actual active import error or just stale historical log
            py_test = self._cmd.run([py_bin, "-c", "import sys; sys.path.insert(0, '/opt/CAPEv2'); import lib.cuckoo.core.startup"])
            if not py_test.success:
                logger.info("Verified active Python import error - attempting environment repair")
                return self.repair_python_env()
            else:
                logger.debug("Python core startup module imports cleanly; ignoring historical journal import error")

        if "already running" in stderr_combined or "cuckoo.pid" in stderr_combined or "address already in use" in stderr_combined or "port" in stderr_combined:
            logger.info("Detected stale instance or port/socket conflict - purging stale processes and PID locks")
            self._cmd.run("pkill -9 -f 'cuckoo.py' || true", shell=True)
            self._cmd.run("pkill -9 -f 'process.py' || true", shell=True)
            self._cmd.run("rm -f /opt/CAPEv2/cuckoo.pid /opt/CAPEv2/storage/cuckoo.pid /tmp/cuckoo-rooter", shell=True)
            return self.repair_cape_services()

        if "permission denied" in stderr_combined:
            logger.info("Detected permission issue")
            return self.repair_cape_permissions()

        logger.warning(f"Could not automatically repair {service_name}")
        return False

    def repair_cape_services(self) -> bool:
        """Purge stale processes, clear locks, rewrite units with correct arguments, and start all CAPEv2 services."""
        logger.info("Performing clean reset and startup of all CAPEv2 systemd services...")
        cape_root = "/opt/CAPEv2"
        venv_py = os.path.join(cape_root, ".venv", "bin", "python")
        py_bin = venv_py if os.path.isfile(venv_py) else "/usr/bin/python3"
        cape_user = "cape"

        # 1. Stop all systemd services first
        for svc in ["cape", "cape-processor", "cape-web", "cape-rooter"]:
            self._cmd.run(["systemctl", "stop", f"{svc}.service"])

        # 2. Force-kill any orphaned processes holding ports, sockets, or PID files
        logger.info("Killing any lingering orphaned CAPE python processes...")
        self._cmd.run("pkill -9 -f 'cuckoo.py' || true", shell=True)
        self._cmd.run("pkill -9 -f 'process.py' || true", shell=True)
        self._cmd.run("pkill -9 -f 'rooter.py' || true", shell=True)
        self._cmd.run("pkill -9 -f 'manage.py runserver' || true", shell=True)

        # 3. Remove stale lock files, PID files, and rooter sockets
        logger.info("Purging stale PID files, locks, and UNIX domain sockets...")
        stale_files = [
            os.path.join(cape_root, "cuckoo.pid"),
            os.path.join(cape_root, "storage", "cuckoo.pid"),
            "/tmp/cuckoo-rooter",
            "/tmp/cuckoo-rooter.sock",
            "/var/run/cuckoo-rooter/rooter.sock",
        ]
        for sf in stale_files:
            try:
                if os.path.exists(sf):
                    os.unlink(sf)
            except Exception:
                pass

        # 4. Enforce correct ownership and libvirt/kvm group membership
        self.repair_cape_permissions(cape_root, cape_user)
        self._cmd.run(["usermod", "-aG", "libvirt,kvm", cape_user])

        # Ensure libvirt-python and crypto helpers are installed inside virtualenv
        check_lv = self._cmd.run([py_bin, "-c", "import libvirt"])
        if not check_lv.success:
            logger.info("Installing missing libvirt-python in CAPE virtual environment...")
            self._cmd.run(["apt-get", "install", "-y", "pkg-config", "libvirt-dev", "python3-libvirt"])
            uv_bin = "/usr/local/bin/uv" if os.path.isfile("/usr/local/bin/uv") else "uv"
            install_res = self._cmd.run([uv_bin, "pip", "install", "--python", py_bin, "libvirt-python", "certvalidator", "asn1crypto", "mscerts"])
            if not install_res.success:
                self._cmd.run([py_bin, "-m", "pip", "install", "--prefer-binary", "libvirt-python", "certvalidator", "asn1crypto", "mscerts"])

        # 5. Synthesize clean systemd service units with verified arguments
        units = {
            "cape-rooter": f"""[Unit]
Description=CAPE Rooter Service
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart={py_bin} {cape_root}/utils/rooter.py -g {cape_user}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""",
            "cape": f"""[Unit]
Description=CAPE Sandbox Service
After=network.target mongodb.service postgresql.service cape-rooter.service
Wants=cape-rooter.service

[Service]
Type=simple
User={cape_user}
Group={cape_user}
WorkingDirectory={cape_root}
Environment=PYTHONPATH={cape_root}
Environment=PYTHONUNBUFFERED=1
ExecStart={py_bin} {cape_root}/cuckoo.py
Restart=always
RestartSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
""",
            "cape-processor": f"""[Unit]
Description=CAPE Processing Engine
After=network.target mongodb.service postgresql.service cape.service
Wants=cape.service

[Service]
Type=simple
User={cape_user}
Group={cape_user}
WorkingDirectory={cape_root}
Environment=PYTHONPATH={cape_root}
Environment=PYTHONUNBUFFERED=1
ExecStart={py_bin} {cape_root}/utils/process.py -p 2 auto
Restart=always
RestartSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
""",
            "cape-web": f"""[Unit]
Description=CAPE Web Interface
After=network.target mongodb.service postgresql.service cape.service

[Service]
Type=simple
User={cape_user}
Group={cape_user}
WorkingDirectory={cape_root}/web
Environment=PYTHONPATH={cape_root}
Environment=PYTHONUNBUFFERED=1
ExecStart={py_bin} manage.py runserver 0.0.0.0:8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""",
        }

        for svc, unit_content in units.items():
            unit_file = f"/etc/systemd/system/{svc}.service"
            try:
                with open(unit_file, "w", encoding="utf-8") as f:
                    f.write(unit_content)
            except Exception as e:
                logger.debug(f"Could not rewrite unit {unit_file}: {e}")

        self._cmd.run(["systemctl", "daemon-reload"])

        # 6. Enable and start in required dependency order with health verification
        services = ["cape-rooter", "cape", "cape-processor", "cape-web"]
        all_ok = True
        import time
        for svc in services:
            svc_name = f"{svc}.service"
            self._cmd.run(["systemctl", "enable", svc_name])
            logger.info(f"Starting {svc_name}...")
            self._cmd.run(["systemctl", "start", svc_name], timeout=30)

            # Poll up to 15 seconds for service to reach 'active' (Python daemons take a few seconds to initialize)
            is_up = False
            state = "unknown"
            for _ in range(15):
                check = self._cmd.run(["systemctl", "is-active", svc_name])
                state = check.stdout.strip()
                if state == "active":
                    is_up = True
                    break
                elif state == "failed":
                    break
                time.sleep(1)

            if is_up:
                logger.info(f"[+] Service {svc} is ACTIVE")
            else:
                j_out = self._cmd.run(["journalctl", "-u", svc_name, "-n", "10", "--no-pager"])
                logger.warning(f"[-] Service {svc} is '{state}', journal:\n{j_out.stdout}")
                self._cmd.run(["systemctl", "restart", svc_name], timeout=30)
                for _ in range(15):
                    check = self._cmd.run(["systemctl", "is-active", svc_name])
                    state = check.stdout.strip()
                    if state == "active":
                        is_up = True
                        break
                    elif state == "failed":
                        break
                    time.sleep(1)

                if is_up:
                    logger.info(f"[+] Service {svc} is ACTIVE on retry")
                else:
                    logger.error(f"[!] Service {svc} failed to reach active state: {state}")
                    all_ok = False
        return all_ok

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

        # On Python > 3.12, poetry cannot build CAPE wheels. Ensure uv is installed
        if not uv_bin and (not poetry_bin or sys.version_info[:2] > (3, 12)):
            logger.info("Installing uv to /usr/local/bin for isolated Python 3.12 environment repair...")
            self._cmd.run(
                'curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh',
                shell=True, timeout=120,
            )
            uv_check = self._cmd.run(["which", "uv"])
            uv_bin = "uv" if uv_check.success else ("/usr/local/bin/uv" if os.path.isfile("/usr/local/bin/uv") else None)

        if uv_bin:
            logger.info("Using uv for environment repair (pinning Python 3.12 for python-flirt / django)")
            uv_env = {
                "UV_HTTP_TIMEOUT": "120",
                "UV_HTTP_CONNECT_TIMEOUT": "15",
                "UV_HTTP_RETRIES": "5",
                "UV_CONCURRENT_DOWNLOADS": "16",
            }
            self._cmd.run([uv_bin, "python", "install", "3.12"], timeout=300, env=uv_env)
            venv_path = os.path.join(cape_root, ".venv")
            venv_py = os.path.join(venv_path, "bin", "python")
            if not os.path.isfile(venv_py):
                self._cmd.run([uv_bin, "venv", "--clear", "--python", "3.12", venv_path], cwd=cape_root, timeout=120, env=uv_env)

            # Ensure pip, setuptools, and wheel exist in virtual environment
            self._cmd.run([uv_bin, "pip", "install", "--python", venv_py, "pip", "setuptools", "wheel"], cwd=cape_root, timeout=120, env=uv_env)

            req_file = os.path.join(cape_root, "requirements.txt")
            result = None

            # METHOD 1: Standard virtualenv pip with --prefer-binary
            if os.path.isfile(req_file):
                logger.info("Repairing environment: installing production dependencies via standard Python pip...")
                result = self._cmd.run(
                    [venv_py, "-m", "pip", "install", "--prefer-binary", "--retries", "5", "--timeout", "30", "-r", "requirements.txt"],
                    cwd=cape_root,
                    timeout=1800,
                    live_output=True,
                )

            # METHOD 2: Fast wheel install fallback (uv pip)
            if not result or not result.success:
                logger.warning("Standard pip encountered issues, attempting uv pip wheel engine...")
                if os.path.isfile(req_file):
                    result = self._cmd.run(
                        [uv_bin, "pip", "install", "--python", venv_py, "-r", "requirements.txt"],
                        cwd=cape_root,
                        timeout=900,
                        live_output=True,
                        env=uv_env,
                    )

            # METHOD 3: uv sync fallback (production only, no dev bloat)
            if not result or not result.success:
                logger.warning("Falling back to uv sync (production dependencies only)...")
                result = self._cmd.run(
                    [uv_bin, "sync", "--no-dev", "--python", "3.12", "--no-install-project"],
                    cwd=cape_root,
                    timeout=1800,
                    live_output=True,
                    env=uv_env,
                )

            # Install CAPEv2 itself
            if result and result.success:
                self._cmd.run(
                    [uv_bin, "pip", "install", "--python", venv_py, "-e", ".", "--no-deps"],
                    cwd=cape_root,
                    timeout=120,
                    env=uv_env,
                )
        elif poetry_bin:
            logger.info("Using poetry for environment repair")
            py_exec = "python3.12" if self._cmd.run(["which", "python3.12"]).success else "python3.11"
            self._cmd.run([poetry_bin, "env", "use", py_exec], cwd=cape_root, timeout=60)
            result = self._cmd.run(
                [poetry_bin, "install"],
                cwd=cape_root,
                timeout=1200,
                live_output=True,
            )
        else:
            logger.error("Neither poetry nor uv found - cannot repair Python env")
            return False

        # Ensure correct ownership for cape service user
        self._cmd.run(["chown", "-R", "cape:cape", cape_root], timeout=60)

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
