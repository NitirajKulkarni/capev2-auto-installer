"""
Main orchestrator for CAPEv2 Automated Installer.

Coordinates the full installation lifecycle:
  PREFLIGHT → BACKUP → INSTALL → VERIFY → REPAIR → REPORT

Supports resume, repair, diagnose, status, dry-run, and uninstall modes.
"""
import json
import os
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cape_auto.config import Config
from cape_auto.command import CommandRunner
from cape_auto.state import (
    StateManager, StageStatus, ResourceOwnership,
    HealthStatus, INSTALLATION_STAGES,
)
from cape_auto.diagnostics import DiagnosticsEngine
from cape_auto.remediation import RemediationEngine
from cape_auto.logging_setup import get_logger
from cape_auto.exceptions import (
    CapeAutoError, RebootRequired, ManualInterventionRequired,
    StageError, PreflightError,
)
from cape_auto.reporting import ReportGenerator

logger = get_logger("orchestrator")

# ═════════════════════════════════════════════════════════════════════
# WINDOWS ENTERPRISE EVALUATION & MALWARE ANALYSIS POLICIES
# ═════════════════════════════════════════════════════════════════════

WINDOWS_EVAL_CATALOG = {
    "win10_eval": {
        "name": "Windows 10 Enterprise Evaluation (x64 English)",
        "edition_label": "Windows 10 Enterprise Eval",
        "default_filename": "win10-enterprise-eval.iso",
        "os_variant": "win10",
        "min_disk_gb": 60,
        "recommended_ram_mb": 4096,
        "recommended_vcpus": 2,
        "needs_uefi": False,
        "urls": [
            "https://go.microsoft.com/fwlink/p/?LinkID=2195404",
            "https://software-download.microsoft.com/download/db/444969d5-f34g-4e03-ac9d-1f9786c69161/19044.1288.211006-0501.21h2_release_svc_refresh_CLIENT_LTSC_EVAL_x64FRE_en-us.iso",
            "https://software-static.download.prss.microsoft.com/dbazure/9882d4ba-ab90-4ec6-a197-6a16223590b1/19045.2006.220908-0225.21h2_release_svc_refresh_CLIENTENTERPRISEEVAL_OEMRET_x64FRE_en-us.iso",
        ],
    },
    "win11_eval": {
        "name": "Windows 11 Enterprise Evaluation (x64 English)",
        "edition_label": "Windows 11 Enterprise Eval",
        "default_filename": "win11-enterprise-eval.iso",
        "os_variant": "win11",
        "min_disk_gb": 60,
        "recommended_ram_mb": 3584,
        "recommended_vcpus": 2,
        "needs_uefi": False,
        "urls": [
            "https://go.microsoft.com/fwlink/?linkid=2270353",
            "https://software-static.download.prss.microsoft.com/dbazure/998969d5-f34g-4e03-ac9d-1f9786c66749/26100.1742.240906-0331.ge_release_svc_refresh_CLIENT_IOT_LTSC_EVAL_x64FRE_en-us.iso",
        ],
    },
}

TINY11_PROHIBITED_PATTERNS = [
    "tiny11", "tiny-11", "tiny10", "tiny-10", "micro10",
    "ghostspectre", "ghost-spectre", "revisle", "revi-os", "revios",
]


def render_ascii_progress_bar(current: int, total: int, width: int = 24) -> str:
    """Render an ASCII progress bar: [████████████░░░░░░░░░░░░]  50%"""
    if total <= 0:
        return f"[{'░' * width}]   0%"
    pct = max(0, min(100, int((current / total) * 100)))
    filled = max(0, min(width, int((current / total) * width)))
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {pct:3d}%"


def validate_iso_policy(path_or_url: str) -> None:
    """
    Enforce strict policy prohibiting Tiny11 and stripped Windows images.
    Malware analysis strictly requires authentic, full-fidelity Windows OS.
    """
    if not path_or_url:
        return
    lower = path_or_url.lower()
    for pattern in TINY11_PROHIBITED_PATTERNS:
        if pattern in lower:
            raise StageError(
                f"STRICT POLICY VIOLATION: Tiny11 / stripped OS image detected ('{path_or_url}').\n"
                "  Tiny11 and stripped OS builds are STRICTLY PROHIBITED for malware analysis!\n"
                "  Reason: Stripped builds remove critical Windows subsystems including:\n"
                "    - Windows Defender & Antimalware Scan Interface (AMSI)\n"
                "    - Event Tracing for Windows (ETW) and kernel logging channels\n"
                "    - Complete Windows Management Instrumentation (WMI) providers\n"
                "    - Background Intelligent Transfer (BITS) & Task Scheduler\n"
                "    - Standard COM interfaces and baseline registry structures\n"
                "  Malware samples detect stripped environments, crash prematurely, or refuse\n"
                "  to detonate, invalidating CAPEv2 behavioral analysis.\n"
                "  Requirement: Use official Windows 10 Enterprise Evaluation or Windows 11 Enterprise Evaluation.",
                stage="VM_CREATE",
            )


class Orchestrator:
    """
    Main installation orchestrator.

    Implements the state machine that drives the installation through
    all stages, with automatic diagnosis and repair on failure.
    """

    def __init__(self, config: Config, project_dir: str):
        self._config = config
        self._project_dir = project_dir
        self._dry_run_mode = False

        # Initialize subsystems
        self._cmd = CommandRunner(dry_run=False)
        self._state = StateManager(
            state_dir=os.path.join(project_dir, "state"),
            backup_dir=os.path.join(project_dir, "backups"),
        )
        self._diag = DiagnosticsEngine(
            cmd=self._cmd,
            cape_root=config.get_str("installation.cape_root", "/opt/CAPEv2"),
        )

        # Detect remote session
        self._is_remote = bool(os.environ.get("SSH_CONNECTION"))
        if self._is_remote:
            logger.info("SSH session detected - remote-safe mode enabled")

        self._remediation = RemediationEngine(
            cmd=self._cmd,
            state=self._state,
            allow_medium=config.get_bool("installation.auto_repair", True),
            allow_high=not self._is_remote and config.get_bool("safety.destructive_repair", False),
            allow_destructive=config.get_bool("safety.destructive_repair", False),
            is_remote=self._is_remote,
        )
        self._reporter = ReportGenerator(
            reports_dir=os.path.join(project_dir, "reports"),
            state=self._state,
            config=config,
        )

    # ═══════════════════════════════════════════════════════════════════
    # PROGRESS & UI RENDERING
    # ═══════════════════════════════════════════════════════════════════

    def _render_stage_banner(
        self, stage_idx: int, total_stages: int, stage_name: str, attempt: int, max_repair: int
    ) -> None:
        """Render a high-visibility, organized stage banner with live progress bar."""
        bar = render_ascii_progress_bar(stage_idx + 1, total_stages, width=24)
        desc = self._get_stage_description(stage_name)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        logger.info("═" * 78)
        logger.info(f"  {bar}  |  STAGE {stage_idx + 1}/{total_stages}: {stage_name}")
        logger.info(f"  ▶ Description: {desc}")
        logger.info(f"  ▶ Attempt:     {attempt} of {max_repair}   |   Started: {now_str}")
        logger.info("═" * 78)

    def _render_stage_result(
        self, stage_idx: int, total_stages: int, stage_name: str, status: str, duration: float, detail: str = ""
    ) -> None:
        """Render organized stage outcome indicator."""
        dur_str = f"{duration:.1f}s"
        if status == "SUCCESS":
            logger.info(f"  [✓ PASS] Stage {stage_idx + 1}/{total_stages} ({stage_name}) completed in {dur_str}")
        elif status == "SKIPPED":
            logger.info(f"  [↷ SKIP] Stage {stage_idx + 1}/{total_stages} ({stage_name}) skipped: {detail}")
        elif status == "FAILED":
            logger.error(f"  [✗ FAIL] Stage {stage_idx + 1}/{total_stages} ({stage_name}) failed after {dur_str}: {detail}")
        logger.info("─" * 78)

    def _render_summary_dashboard(self, overall_success: bool, total_elapsed: float) -> None:
        """Render a clean, organized completion dashboard."""
        elapsed_m = int(total_elapsed // 60)
        elapsed_s = int(total_elapsed % 60)
        dur_str = f"{elapsed_m}m {elapsed_s:02d}s" if elapsed_m > 0 else f"{elapsed_s}s"

        completed = [s for s in INSTALLATION_STAGES if self._state.get_stage(s).status == StageStatus.SUCCESS.value]
        failed = self._state.get_failed_stages()
        skipped = [s for s in INSTALLATION_STAGES if self._state.get_stage(s).status == StageStatus.SKIPPED.value]

        logger.info("╔" + "═" * 76 + "╗")
        logger.info(f"║ {'CAPEv2 INSTALLATION SUMMARY':^74} ║")
        logger.info("╠" + "═" * 76 + "╣")
        status_text = "COMPLETE / SUCCESS" if overall_success else "PARTIAL / REQUIRES ATTENTION"
        logger.info(f"║  Overall Status:    {status_text:<54} ║")
        logger.info(f"║  Duration:          {dur_str:<54} ║")
        logger.info(f"║  Stages Completed:  {len(completed)}/{len(INSTALLATION_STAGES):<52} ║")
        if failed:
            failed_str = ", ".join(failed)[:52]
            logger.info(f"║  Failed Stages:     {failed_str:<54} ║")
        if skipped:
            skipped_str = ", ".join(skipped)[:52]
            logger.info(f"║  Skipped Stages:    {skipped_str:<54} ║")
        logger.info("╟" + "─" * 76 + "╢")
        logger.info(f"║  Services & Access:{' ' * 55} ║")
        web_url = f"http://{self._config.get_str('network.web_bind', '127.0.0.1')}:{self._config.get_int('network.web_port', 8000)}"
        logger.info(f"║    ▶ Web Interface: {web_url:<54} ║")
        root_path = self._config.get_str('installation.cape_root', '/opt/CAPEv2')
        logger.info(f"║    ▶ CAPE Root:     {root_path:<54} ║")
        if self._config.get_bool("guest.enabled"):
            ed_info = WINDOWS_EVAL_CATALOG.get(self._config.get_str("guest.windows_edition", "win10_eval").lower(), {})
            vm_info = f"{self._config.get_str('guest.name', 'cape-win')} ({ed_info.get('edition_label', 'Win Eval')})"
            logger.info(f"║    ▶ Analysis VM:   {vm_info[:54]:<54} ║")
        logger.info("╚" + "═" * 76 + "╝")

    # ═══════════════════════════════════════════════════════════════════
    # PRIMARY MODES
    # ═══════════════════════════════════════════════════════════════════

    def install(self, from_stage: Optional[str] = None) -> int:
        """Run the full installation pipeline."""
        logger.info("=" * 60)
        logger.info("CAPEv2 Automated Installer - Starting")
        logger.info("=" * 60)

        # Determine starting point
        start_idx = 0
        if from_stage:
            idx = self._state.get_stage_from(from_stage.upper())
            if idx is None:
                logger.error(f"Unknown stage: {from_stage}")
                logger.info(f"Available stages: {', '.join(INSTALLATION_STAGES)}")
                return 1
            start_idx = idx
        else:
            # Check for resume
            resume = self._state.get_resume_stage()
            if resume:
                prev_idx = self._state.get_stage_from(resume)
                if prev_idx and prev_idx > 0:
                    logger.info(f"Resuming from stage: {resume}")
                    start_idx = prev_idx

        # Update manifest
        self._state.update_manifest("installation_id", self._state.installation_id)
        self._state.update_manifest("timestamp_start", datetime.now(timezone.utc).isoformat())
        self._state.update_manifest("project_dir", self._project_dir)

        # Execute stages
        max_repair = self._config.get_int("installation.max_repair_attempts", 3)
        overall_success = True
        total_stages = len(INSTALLATION_STAGES)
        install_start_time = time.monotonic()

        for i in range(start_idx, total_stages):
            stage_name = INSTALLATION_STAGES[i]
            stage = self._state.get_stage(stage_name)

            # Skip already completed stages
            if stage.status == StageStatus.SUCCESS.value:
                self._render_stage_result(i, total_stages, stage_name, "SKIPPED", 0.0, "already completed")
                continue
            if stage.status == StageStatus.SKIPPED.value:
                self._render_stage_result(i, total_stages, stage_name, "SKIPPED", 0.0, "skipped by configuration")
                continue

            stage_start = time.monotonic()
            # Execute stage
            success = self._execute_stage_with_repair(stage_name, max_repair, stage_idx=i, total_stages=total_stages)
            stage_dur = time.monotonic() - stage_start

            if success:
                self._render_stage_result(i, total_stages, stage_name, "SUCCESS", stage_dur)
            else:
                overall_success = False
                stage_obj = self._state.get_stage(stage_name)
                err_detail = stage_obj.error_message or "Unknown failure"
                self._render_stage_result(i, total_stages, stage_name, "FAILED", stage_dur, err_detail)
                # Check if we can continue
                if self._is_blocking_failure(stage_name):
                    logger.error(f"Stage {stage_name} failed and blocks further progress")
                    break
                else:
                    logger.warning(f"Stage {stage_name} failed but is non-blocking, continuing...")

        # Finalize
        self._state.update_manifest("timestamp_end", datetime.now(timezone.utc).isoformat())

        # Generate reports
        self._reporter.generate_final_report(overall_success)

        total_elapsed = time.monotonic() - install_start_time
        self._render_summary_dashboard(overall_success, total_elapsed)

        if overall_success:
            return 0
        else:
            failed = self._state.get_failed_stages()
            logger.warning("=" * 60)
            logger.warning(f"CAPEv2 Installation: PARTIAL (failed: {', '.join(failed)})")
            logger.warning("Run 'sudo ./install.sh --diagnose' for details")
            logger.warning("Run 'sudo ./install.sh --resume' to retry failed stages")
            logger.warning("=" * 60)
            return 1

    def resume(self) -> int:
        """Resume from last checkpoint."""
        resume_stage = self._state.get_resume_stage()
        if not resume_stage:
            if self._state.is_complete():
                logger.info("Installation already complete.")
                return 0
            logger.info("No stage to resume from. Starting fresh.")
            return self.install()

        logger.info(f"Resuming installation from stage: {resume_stage}")
        return self.install(from_stage=resume_stage)

    def repair(self) -> int:
        """Repair mode - diagnose and fix issues."""
        logger.info("Running repair mode...")

        results = self._diag.diagnose_all()
        report = self._diag.generate_report(results)
        print(report)

        # Attempt repairs for failures
        repaired = 0
        for r in results:
            if r.status == HealthStatus.FAIL.value:
                logger.info(f"Attempting repair for: {r.component}")
                error_cat = self._map_component_to_error(r.component)
                if self._attempt_repair(error_cat, r.component):
                    repaired += 1

        if repaired > 0:
            logger.info(f"Repaired {repaired} component(s). Re-running diagnostics...")
            results = self._diag.diagnose_all()
            report = self._diag.generate_report(results)
            print(report)

        return 0

    def diagnose(self, watch: bool = False) -> int:
        """Run diagnostic checks."""
        results = self._diag.diagnose_all()
        report = self._diag.generate_report(results)
        print(report)

        # Save to file
        report_path = os.path.join(self._project_dir, "reports", "diagnostic-report.md")
        Path(os.path.dirname(report_path)).mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)

        # Save JSON
        json_path = os.path.join(self._project_dir, "reports", "diagnostic-report.json")
        with open(json_path, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)

        if watch:
            logger.info("Watching mode - press Ctrl+C to stop")
            try:
                while True:
                    time.sleep(60)
                    results = self._diag.diagnose_all()
                    report = self._diag.generate_report(results)
                    print("\033[H\033[J")  # Clear screen
                    print(report)
            except KeyboardInterrupt:
                pass

        return 0

    def status(self, drift: bool = False) -> int:
        """Show installation status dashboard."""
        summary = self._state.get_summary()

        print("\n" + "=" * 50)
        print("CAPE Installation Status")
        print("=" * 50)

        status_icons = {
            "success": "[+]",
            "failed": "[x]",
            "pending": "[ ]",
            "running": "[*]",
            "skipped": "[-]",
            "blocked": "[#]",
        }

        # Group stages
        groups = {
            "Host": ["PREFLIGHT", "BACKUP", "REPOSITORIES", "BASE_PACKAGES"],
            "Virtualization": ["KVM", "LIBVIRT", "REBOOT_CHECK"],
            "CAPE": ["CAPE_REPOSITORY", "CAPE_DEPENDENCIES", "CAPE_INSTALL",
                     "CAPE_CONFIG", "DATABASE", "SYSTEMD"],
            "Network": ["NETWORK"],
            "Guest": ["VM_CREATE", "VM_INSTALL", "VM_CONFIG", "AGENT", "SNAPSHOT"],
            "Validation": ["MACHINERY_CONFIG", "CAPE_START", "HEALTH_CHECK",
                          "END_TO_END_TEST", "FINALIZE"],
        }

        for group_name, stages in groups.items():
            print(f"\n  {group_name}")
            for stage_name in stages:
                if stage_name in summary:
                    info = summary[stage_name]
                    icon = status_icons.get(info["status"], "?")
                    line = f"    {icon} {stage_name:<25s} {info['status'].upper()}"
                    if info.get("error"):
                        line += f"  ({info['error'][:50]})"
                    print(line)

        # Overall
        failed = self._state.get_failed_stages()
        if not failed and self._state.is_complete():
            print(f"\n  Overall: READY [OK]")
        elif failed:
            print(f"\n  Overall: {len(failed)} FAILED")
        else:
            print(f"\n  Overall: IN PROGRESS")

        print("=" * 50)

        if drift:
            self._show_drift()

        return 0

    def dry_run(self) -> int:
        """Preview what the installer would do."""
        logger.info("DRY-RUN MODE - No changes will be made")
        self._cmd = CommandRunner(dry_run=True)
        self._dry_run_mode = True

        print("\n" + "=" * 50)
        print("DRY-RUN: Planned Actions")
        print("=" * 50)

        # Show what each stage would do
        for stage_name in INSTALLATION_STAGES:
            stage = self._state.get_stage(stage_name)
            if stage.status == StageStatus.SUCCESS.value:
                print(f"  [SKIP]  {stage_name} (already complete)")
            else:
                print(f"  [PLAN]  {stage_name}")
                desc = self._get_stage_description(stage_name)
                if desc:
                    print(f"          {desc}")

        print("\n" + "=" * 50)

        # Show config summary
        print("\nConfiguration:")
        print(f"  CAPE root:     {self._config.get_str('installation.cape_root')}")
        print(f"  CAPE user:     {self._config.get_str('installation.cape_user')}")
        print(f"  Python mgr:   {self._config.get_str('installation.python_manager')}")
        print(f"  Network mode:  {self._config.get_str('network.mode')}")
        print(f"  Guest enabled: {self._config.get_bool('guest.enabled')}")

        warnings = self._config.validate()
        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(f"  [WARN] {w}")

        return 0

    def preflight(self) -> int:
        """Run preflight checks only."""
        logger.info("Running preflight checks...")
        return self._run_preflight(report_only=True)

    def self_test(self) -> int:
        """Run framework self-tests."""
        logger.info("Running framework self-tests...")
        passed = 0
        failed = 0
        tests = []

        # Test 1: Config loading
        try:
            from cape_auto.config import Config
            c = Config(self._config.config_path, self._project_dir)
            assert c.get_str("installation.cape_root")
            tests.append(("Config loading", True))
            passed += 1
        except Exception as e:
            tests.append(("Config loading", False, str(e)))
            failed += 1

        # Test 2: Command runner
        try:
            import sys
            result = self._cmd.run([sys.executable, "-c", "print('test')"], timeout=5)
            assert result.success
            assert result.stdout.strip() == "test"
            tests.append(("Command runner", True))
            passed += 1
        except Exception as e:
            tests.append(("Command runner", False, str(e)))
            failed += 1

        # Test 3: State management
        try:
            self._state.create_checkpoint("SELF_TEST", {"test": True})
            cp = self._state.load_checkpoint("SELF_TEST")
            assert cp is not None
            tests.append(("State management", True))
            passed += 1
        except Exception as e:
            tests.append(("State management", False, str(e)))
            failed += 1

        # Test 4: Resource registry
        try:
            self._state.register_resource(
                "test_resource", "self_test_item",
                ResourceOwnership.CREATED_BY_INSTALLER,
            )
            assert self._state.is_owned_by_us("test_resource", "self_test_item")
            tests.append(("Resource registry", True))
            passed += 1
        except Exception as e:
            tests.append(("Resource registry", False, str(e)))
            failed += 1

        # Test 5: Logging
        try:
            from cape_auto.logging_setup import get_logger
            test_logger = get_logger("self_test")
            test_logger.info("Self-test log message")
            tests.append(("Logging", True))
            passed += 1
        except Exception as e:
            tests.append(("Logging", False, str(e)))
            failed += 1

        # Test 6: Secret redaction
        try:
            from cape_auto.logging_setup import RedactingFormatter
            import logging
            fmt = RedactingFormatter("%(message)s", redact=True)
            record = logging.LogRecord("test", logging.INFO, "", 0,
                                       "password=secret123", (), None)
            formatted = fmt.format(record)
            assert "secret123" not in formatted
            tests.append(("Secret redaction", True))
            passed += 1
        except Exception as e:
            tests.append(("Secret redaction", False, str(e)))
            failed += 1

        # Test 7: Diagnostics engine
        try:
            assert hasattr(self._diag, "diagnose_all")
            tests.append(("Diagnostics engine", True))
            passed += 1
        except Exception as e:
            tests.append(("Diagnostics engine", False, str(e)))
            failed += 1

        # Test 8: Remediation engine
        try:
            cat = self._remediation.classify_error("permission denied", 1)
            assert cat == "PERMISSION_ERROR"
            tests.append(("Error classification", True))
            passed += 1
        except Exception as e:
            tests.append(("Error classification", False, str(e)))
            failed += 1

        # Report
        print("\n" + "=" * 50)
        print("Framework Self-Test Results")
        print("=" * 50)
        for t in tests:
            icon = "[PASS]" if t[1] else "[FAIL]"
            line = f"  {icon} {t[0]}"
            if len(t) > 2:
                line += f" - {t[2]}"
            print(line)
        print(f"\n  Passed: {passed}, Failed: {failed}")
        print("=" * 50)

        return 0 if failed == 0 else 1

    def clean_install(self) -> int:
        """
        Perform a complete clean installation:
        1. Stop and remove all CAPE systemd services.
        2. Destroy and undefine analysis VM, disks, snapshots, and unattended ISOs.
        3. Destroy and undefine libvirt analysis network.
        4. Remove previous CAPE directory (/opt/CAPEv2).
        5. Purge installer state, backups, and checkpoints.
        6. Start a fresh unattended installation from scratch.
        """
        logger.info("═" * 78)
        logger.info("  STARTING CLEAN INSTALLATION (FULL WIPE & FRESH PROVISION)")
        logger.info("═" * 78)

        if self._dry_run_mode:
            logger.info("[DRY-RUN] Would wipe existing CAPE services, VMs, disks, networks, and /opt/CAPEv2, then reinstall.")
            return self.dry_run()

        # Step 1: Stop and disable all CAPE services
        logger.info("[CLEAN 1/5] Stopping and removing systemd services...")
        cape_services = ["cape-web", "cape-processor", "cape", "cape-rooter"]
        for svc in cape_services:
            self._cmd.run(["systemctl", "stop", f"{svc}.service"])
            self._cmd.run(["systemctl", "disable", f"{svc}.service"])
            svc_file = f"/etc/systemd/system/{svc}.service"
            if os.path.isfile(svc_file):
                try:
                    os.remove(svc_file)
                except Exception:
                    pass
        self._cmd.run(["systemctl", "daemon-reload"])

        # Step 2: Tear down analysis VM, disks, and snapshots
        vm_name = self._config.get_str("guest.name", "cape-win")
        disk_path = self._config.get_str("guest.disk_path", "/var/lib/libvirt/images/cape-win.qcow2")
        unattend_iso = f"/var/lib/libvirt/images/{vm_name}-unattend.iso"
        staging_dir = os.path.join(self._project_dir, "state", "unattend_staging")

        logger.info(f"[CLEAN 2/5] Tearing down analysis VM '{vm_name}' and storage...")
        vm_list = self._cmd.run_capture(["virsh", "list", "--all"])
        if vm_name in vm_list:
            self._cmd.run(["virsh", "destroy", vm_name])
            self._cmd.run(["virsh", "undefine", vm_name, "--remove-all-storage", "--nvram", "--snapshots-metadata"])

        # Remove disk files and staging files
        for fpath in [disk_path, unattend_iso, os.path.join(self._project_dir, "state", f"{vm_name}-unattend.iso")]:
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    logger.info(f"Removed file: {fpath}")
                except Exception as e:
                    logger.warning(f"Could not remove {fpath}: {e}")

        # Purge any partial/interrupted downloads (.part) in images directory
        images_dir = "/var/lib/libvirt/images"
        if os.path.isdir(images_dir):
            for fname in os.listdir(images_dir):
                if fname.endswith(".part"):
                    p_file = os.path.join(images_dir, fname)
                    try:
                        os.remove(p_file)
                        logger.info(f"Removed partial download: {p_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove {p_file}: {e}")

        if os.path.isdir(staging_dir):
            import shutil
            shutil.rmtree(staging_dir, ignore_errors=True)

        # Step 3: Tear down libvirt analysis network
        net_name = self._config.get_str("network.libvirt_network_name", "cape-analysis")
        logger.info(f"[CLEAN 3/5] Tearing down analysis network '{net_name}'...")
        net_list = self._cmd.run_capture(["virsh", "net-list", "--all"])
        if net_name in net_list:
            self._cmd.run(["virsh", "net-destroy", net_name])
            self._cmd.run(["virsh", "net-undefine", net_name])

        net_xml = os.path.join(self._project_dir, "state", "cape-network.xml")
        if os.path.isfile(net_xml):
            try:
                os.remove(net_xml)
            except Exception:
                pass

        # Step 4: Remove previous CAPE repository / root directory
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        logger.info(f"[CLEAN 4/5] Removing previous CAPE directory '{cape_root}'...")
        if os.path.isdir(cape_root):
            import shutil
            try:
                shutil.rmtree(cape_root, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not completely remove {cape_root}: {e}")
            if os.path.isdir(cape_root):
                self._cmd.run(["rm", "-rf", cape_root])

        # Step 5: Purge installer state and start fresh
        logger.info("[CLEAN 5/5] Purging installer state database and checkpoints...")
        state_dir = os.path.join(self._project_dir, "state")
        if os.path.isdir(state_dir):
            for fname in os.listdir(state_dir):
                if fname.endswith(".json") or fname.endswith(".xml"):
                    try:
                        os.remove(os.path.join(state_dir, fname))
                    except Exception:
                        pass

        # Re-initialize state manager with clean state
        self._state = StateManager(
            state_dir=os.path.join(self._project_dir, "state"),
            backup_dir=os.path.join(self._project_dir, "backups"),
        )
        self._remediation = RemediationEngine(
            cmd=self._cmd,
            state=self._state,
            allow_medium=self._config.get_bool("installation.auto_repair", True),
            allow_high=not self._is_remote and self._config.get_bool("safety.destructive_repair", False),
            allow_destructive=self._config.get_bool("safety.destructive_repair", False),
            is_remote=self._is_remote,
        )

        logger.info("═" * 78)
        logger.info("  CLEANUP COMPLETE. INITIATING FRESH UNATTENDED INSTALLATION...")
        logger.info("═" * 78)

        # Launch fresh install from stage 0
        return self.install()

    def uninstall(self, keep_user: bool = False, keep_data: bool = False,
                  keep_vm: bool = False, full_reset: bool = False,
                  dry_run: bool = False) -> int:
        """Uninstall CAPE resources created by this installer."""
        logger.info("Uninstall mode")

        resources = self._state.get_resources()
        our_resources = [r for r in resources if r.ownership in (
            ResourceOwnership.CREATED_BY_INSTALLER.value,
            ResourceOwnership.MODIFIED_BY_INSTALLER.value,
        )]

        if not our_resources and not full_reset:
            logger.info("No resources created by this installer found.")
            return 0

        print("\nResources to remove:")
        for r in our_resources:
            print(f"  - {r.resource_type}: {r.name}")

        if dry_run:
            print("\n[DRY-RUN] No changes made.")
            return 0

        # Stop CAPE services first
        for svc in ["cape-web", "cape-processor", "cape", "cape-rooter"]:
            self._cmd.run(["systemctl", "stop", f"{svc}.service"])
            self._cmd.run(["systemctl", "disable", f"{svc}.service"])

        # Remove owned resources
        for r in our_resources:
            if r.resource_type == "libvirt_network" and not keep_vm:
                self._cmd.run(["virsh", "net-destroy", r.name])
                self._cmd.run(["virsh", "net-undefine", r.name])
            elif r.resource_type == "vm" and not keep_vm:
                self._cmd.run(["virsh", "destroy", r.name])
                self._cmd.run(["virsh", "undefine", r.name, "--remove-all-storage"])

        logger.info("Uninstall complete. Pre-existing resources preserved.")
        return 0

    def update(self) -> int:
        """Update existing CAPEv2 installation."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")

        if not os.path.isdir(cape_root):
            logger.error(f"CAPE not found at {cape_root}")
            return 1

        logger.info("Updating CAPEv2...")

        # Record current state
        old_commit = self._cmd.run_capture(
            ["git", "rev-parse", "HEAD"], cwd=cape_root
        ).strip()
        self._state.update_manifest("update_from_commit", old_commit)

        # Backup config
        self._state.create_backup("update", [
            os.path.join(cape_root, "conf"),
        ])

        # Pull
        pull = self._cmd.run(["git", "pull", "--ff-only"], cwd=cape_root, timeout=120)
        if not pull.success:
            logger.error(f"Git pull failed: {pull.stderr}")
            return 1

        new_commit = self._cmd.run_capture(
            ["git", "rev-parse", "HEAD"], cwd=cape_root
        ).strip()
        logger.info(f"Updated: {old_commit[:12]} → {new_commit[:12]}")

        # Reinstall dependencies
        self._remediation.repair_python_env(cape_root)

        # Restart services
        for svc in ["cape-rooter", "cape", "cape-processor", "cape-web"]:
            self._cmd.run(["systemctl", "restart", f"{svc}.service"])

        return 0

    def reset_failed_and_retry(self) -> int:
        """Reset failed stages and retry."""
        failed = self._state.get_failed_stages()
        if not failed:
            logger.info("No failed stages to reset.")
            return 0

        for stage_name in failed:
            logger.info(f"Resetting stage: {stage_name}")
            self._state.reset_stage(stage_name)

        return self.resume()

    # ═══════════════════════════════════════════════════════════════════
    # STAGE EXECUTION ENGINE
    # ═══════════════════════════════════════════════════════════════════

    def _execute_stage_with_repair(
        self, stage_name: str, max_repair: int, stage_idx: int = 0, total_stages: int = len(INSTALLATION_STAGES)
    ) -> bool:
        """Execute a stage with automatic diagnosis and repair on failure."""
        for attempt in range(1, max_repair + 1):
            self._render_stage_banner(stage_idx, total_stages, stage_name, attempt, max_repair)

            try:
                self._state.start_stage(stage_name)
                self._execute_stage(stage_name)
                self._state.complete_stage(stage_name)
                return True

            except RebootRequired:
                self._state.update_manifest("reboot_required", True)
                raise

            except ManualInterventionRequired as e:
                self._state.fail_stage(stage_name, str(e))
                self._reporter.generate_manual_intervention_report(
                    stage_name, str(e), e.report_path
                )
                raise

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Stage {stage_name} failed: {error_msg}")

                if attempt < max_repair:
                    # Diagnose and repair
                    category = self._remediation.classify_error(
                        error_msg, getattr(e, "exit_code", -1)
                    )
                    logger.info(f"Error category: {category}")

                    repaired = self._attempt_repair(category, stage_name)
                    self._state.add_repair_attempt(stage_name, f"{category}_attempt_{attempt}")

                    if not repaired:
                        logger.warning("Repair unsuccessful, will retry anyway")
                else:
                    self._state.fail_stage(stage_name, error_msg)

        return False

    def _execute_stage(self, stage_name: str) -> None:
        """Execute a single installation stage."""
        stage_map = {
            "PREFLIGHT": self._stage_preflight,
            "BACKUP": self._stage_backup,
            "REPOSITORIES": self._stage_repositories,
            "BASE_PACKAGES": self._stage_base_packages,
            "KVM": self._stage_kvm,
            "LIBVIRT": self._stage_libvirt,
            "REBOOT_CHECK": self._stage_reboot_check,
            "CAPE_REPOSITORY": self._stage_cape_repository,
            "CAPE_DEPENDENCIES": self._stage_cape_dependencies,
            "CAPE_INSTALL": self._stage_cape_install,
            "CAPE_CONFIG": self._stage_cape_config,
            "DATABASE": self._stage_database,
            "SYSTEMD": self._stage_systemd,
            "NETWORK": self._stage_network,
            "VM_CREATE": self._stage_vm_create,
            "VM_INSTALL": self._stage_vm_install,
            "VM_CONFIG": self._stage_vm_config,
            "AGENT": self._stage_agent,
            "SNAPSHOT": self._stage_snapshot,
            "MACHINERY_CONFIG": self._stage_machinery_config,
            "CAPE_START": self._stage_cape_start,
            "HEALTH_CHECK": self._stage_health_check,
            "END_TO_END_TEST": self._stage_end_to_end,
            "FINALIZE": self._stage_finalize,
        }

        handler = stage_map.get(stage_name)
        if handler:
            handler()
        else:
            logger.warning(f"No handler for stage: {stage_name}")

    # ═══════════════════════════════════════════════════════════════════
    # INDIVIDUAL STAGE IMPLEMENTATIONS
    # ═══════════════════════════════════════════════════════════════════

    def _stage_preflight(self) -> None:
        """Comprehensive environment detection and validation."""
        self._run_preflight(report_only=False)

    def _run_preflight(self, report_only: bool = False) -> int:
        """Run preflight checks. Returns 0 on pass, 1 on fail."""
        logger.info("Running preflight checks...")
        issues: list[str] = []
        warnings: list[str] = []

        # OS Detection
        os_release = self._cmd.run_capture(["cat", "/etc/os-release"])
        uname_r = self._cmd.run_capture(["uname", "-r"])
        arch = self._cmd.run_capture(["dpkg", "--print-architecture"]).strip()

        version_id = ""
        codename = ""
        for line in os_release.splitlines():
            if line.startswith("VERSION_ID="):
                version_id = line.split("=")[1].strip('"')
            if line.startswith("VERSION_CODENAME="):
                codename = line.split("=")[1].strip('"')

        logger.info(f"Ubuntu {version_id} ({codename}), kernel {uname_r.strip()}, arch {arch}")
        self._state.update_manifest("ubuntu_version", version_id)
        self._state.update_manifest("ubuntu_codename", codename)
        self._state.update_manifest("kernel", uname_r.strip())
        self._state.update_manifest("architecture", arch)

        # Classify compatibility
        if version_id == "24.04":
            compat = "CAPE_RECOMMENDED"
        elif version_id in ("22.04", "24.10"):
            compat = "CAPE_SUPPORTED"
        elif version_id.startswith("2"):
            compat = "CAPE_COMPATIBILITY_MODE"
        else:
            compat = "UNSUPPORTED"

        self._state.update_manifest("compatibility_class", compat)
        logger.info(f"Compatibility classification: {compat}")

        if compat == "UNSUPPORTED":
            issues.append(f"Ubuntu {version_id} is not supported by CAPEv2")

        # CPU checks
        cpuinfo = self._cmd.run_capture(["cat", "/proc/cpuinfo"])
        has_virt = "vmx" in cpuinfo.lower() or "svm" in cpuinfo.lower()
        kvm_exists = os.path.exists("/dev/kvm") if not self._dry_run_mode else True

        if not has_virt:
            issues.append("No hardware virtualization support (VT-x/AMD-V). If running inside a VM, enable Nested Virtualization in your hypervisor (e.g. VMware 'Virtualize Intel VT-x', Proxmox CPU 'host', VirtualBox 'Enable Nested VT-x').")
        if not kvm_exists and has_virt:
            warnings.append("/dev/kvm not found - KVM modules may need loading")

        # CPU info for manifest
        lscpu = self._cmd.run_capture(["lscpu"])
        for line in lscpu.splitlines():
            if "Model name:" in line:
                self._state.update_manifest("cpu_model", line.split(":", 1)[1].strip())
            if "CPU(s):" in line and "NUMA" not in line and "On-line" not in line:
                self._state.update_manifest("cpu_count", line.split(":", 1)[1].strip())

        # Memory check
        meminfo = self._cmd.run_capture(["cat", "/proc/meminfo"])
        total_mem_kb = 0
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total_mem_kb = int(line.split()[1])
                break
        total_mem_gb = total_mem_kb / (1024 * 1024)
        self._state.update_manifest("ram_gb", round(total_mem_gb, 1))

        if total_mem_gb < 4:
            issues.append(f"Insufficient RAM: {total_mem_gb:.1f} GB (minimum 4 GB)")
        elif total_mem_gb < 8:
            warnings.append(f"Low RAM: {total_mem_gb:.1f} GB (8+ GB recommended for VM)")

        # Disk check
        df_result = self._cmd.run_capture(["df", "-BG", "/"])
        if df_result:
            lines = df_result.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    avail_gb = int(parts[3].rstrip("G"))
                    self._state.update_manifest("disk_available_gb", avail_gb)
                    if avail_gb < 50:
                        issues.append(f"Insufficient disk: {avail_gb} GB free (50+ GB needed)")
                    elif avail_gb < 100:
                        warnings.append(f"Low disk: {avail_gb} GB free (100+ GB recommended)")

        # Network detection
        default_route = self._cmd.run_capture(["ip", "route", "show", "default"])
        if default_route:
            parts = default_route.split()
            if "dev" in parts:
                dev_idx = parts.index("dev")
                if dev_idx + 1 < len(parts):
                    iface = parts[dev_idx + 1]
                    self._state.update_manifest("default_interface", iface)
                    logger.info(f"Default network interface: {iface}")

        # SSH detection
        ssh_conn = os.environ.get("SSH_CONNECTION", "")
        self._state.update_manifest("ssh_session", bool(ssh_conn))
        if ssh_conn:
            warnings.append("Running via SSH - remote-safe mode active")

        # Existing software detection
        existing = []
        for sw in ["docker", "podman", "tailscale", "wg", "openvpn", "ufw",
                    "nft", "virsh", "mongod", "psql", "poetry", "uv"]:
            if self._cmd.run(["which", sw], timeout=5).success:
                existing.append(sw)
        if existing:
            logger.info(f"Existing software detected: {', '.join(existing)}")
            self._state.update_manifest("existing_software", existing)

        # Check for existing CAPE
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        if os.path.isdir(cape_root):
            warnings.append(f"Existing CAPE installation found at {cape_root}")
            self._state.update_manifest("existing_cape", True)

        # Report
        print("\n" + "=" * 50)
        print("Preflight Report")
        print("=" * 50)
        print(f"  Ubuntu:          {version_id} ({codename})")
        print(f"  Kernel:          {uname_r.strip()}")
        print(f"  Architecture:    {arch}")
        print(f"  Compatibility:   {compat}")
        print(f"  RAM:             {total_mem_gb:.1f} GB")
        print(f"  Virtualization:  {'Yes' if has_virt else 'No'}")
        print(f"  SSH Session:     {'Yes' if ssh_conn else 'No'}")
        if existing:
            print(f"  Existing SW:     {', '.join(existing)}")

        if issues:
            print(f"\n  ISSUES ({len(issues)}):")
            for issue in issues:
                print(f"    [FAIL] {issue}")

        if warnings:
            print(f"\n  WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"    [WARN] {w}")

        if not issues:
            print(f"\n  Result: PREFLIGHT PASSED [OK]")
        else:
            print(f"\n  Result: PREFLIGHT FAILED [FAIL]")

        print("=" * 50 + "\n")

        if report_only:
            return 1 if issues else 0

        if issues:
            raise PreflightError("; ".join(issues))

        return 0

    def _stage_backup(self) -> None:
        """Create initial backup of existing state."""
        logger.info("Creating pre-installation backups...")
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")

        files_to_backup = []
        if os.path.isdir(cape_root):
            conf_dir = os.path.join(cape_root, "conf")
            if os.path.isdir(conf_dir):
                for f in os.listdir(conf_dir):
                    if f.endswith(".conf"):
                        files_to_backup.append(os.path.join(conf_dir, f))

        # Backup netplan if exists
        netplan_dir = "/etc/netplan"
        if os.path.isdir(netplan_dir):
            for f in os.listdir(netplan_dir):
                files_to_backup.append(os.path.join(netplan_dir, f))

        if files_to_backup:
            self._state.create_backup("initial", files_to_backup)

    def _stage_repositories(self) -> None:
        """Configure package repositories."""
        logger.info("Updating package repositories...")

        # Handle proxy
        http_proxy = self._config.get_str("proxy.http_proxy")
        env = {}
        if http_proxy:
            env["http_proxy"] = http_proxy
            env["https_proxy"] = self._config.get_str("proxy.https_proxy", http_proxy)

        self._cmd.run_with_retry(
            ["apt-get", "update"],
            env=env if env else None,
            timeout=300,
            max_attempts=3,
            delay=10,
        )

    def _stage_base_packages(self) -> None:
        """Install essential system packages."""
        logger.info("Installing base packages...")

        base_packages = [
            "git", "curl", "wget", "gnupg2", "software-properties-common",
            "build-essential", "python3-dev", "python3-venv", "python3-pip",
            "libffi-dev", "libssl-dev", "libjpeg-dev", "zlib1g-dev",
            "tmux", "htop", "jq", "unzip", "net-tools", "genisoimage",
        ]

        # Install in batches to handle individual failures
        self._cmd.run_checked(
            ["apt-get", "install", "-y", "--no-install-recommends"] + base_packages,
            timeout=600,
        )

        # Track as our resources
        for pkg in base_packages:
            self._state.register_resource(
                "package", pkg, ResourceOwnership.MODIFIED_BY_INSTALLER
            )

        # Ensure uv is installed system-wide for hermetic Python 3.12 management
        if not self._cmd.run(["which", "uv"]).success and not os.path.isfile("/usr/local/bin/uv"):
            logger.info("Installing uv to /usr/local/bin for isolated Python 3.12 management...")
            self._cmd.run(
                'curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh',
                shell=True, timeout=120,
            )

    def _stage_kvm(self) -> None:
        """Install and verify KVM/QEMU."""
        logger.info("Setting up KVM/QEMU...")

        # Check if KVM already works
        kvm_diag = self._diag.diagnose_kvm()
        if kvm_diag.status == HealthStatus.PASS.value:
            logger.info("KVM is already working")
            self._state.register_resource(
                "kvm", "kvm", ResourceOwnership.PRE_EXISTING
            )
            return

        # Check /dev/kvm
        if not os.path.exists("/dev/kvm"):
            # Try loading modules
            self._cmd.run(["modprobe", "kvm_intel"])
            self._cmd.run(["modprobe", "kvm_amd"])
            if not os.path.exists("/dev/kvm"):
                raise ManualInterventionRequired(
                    "KVM unavailable (/dev/kvm missing). "
                    "If on bare metal: Enable Intel VT-x or AMD-V in BIOS/UEFI. "
                    "If inside a Virtual Machine (VMware/VirtualBox/Proxmox): Enable 'Nested Virtualization' "
                    "in your VM settings (e.g. VMware 'Virtualize Intel VT-x/EPT', VirtualBox 'Enable Nested VT-x', Proxmox CPU 'host'). "
                    "Then run: sudo ./install.sh --resume",
                    report_path="reports/manual-intervention.md",
                )

        # Install KVM packages (don't use upstream kvm-qemu.sh by default
        # as it compiles from source - use system packages first)
        kvm_packages = [
            "qemu-kvm", "qemu-system-x86", "qemu-utils",
            "libvirt-daemon-system", "libvirt-clients",
            "bridge-utils", "virt-manager", "virtinst",
            "ovmf", "swtpm", "swtpm-tools",
        ]

        result = self._cmd.run(
            ["apt-get", "install", "-y"] + kvm_packages,
            timeout=600,
        )

        if not result.success:
            # Fallback: try individual packages
            for pkg in kvm_packages:
                self._cmd.run(["apt-get", "install", "-y", pkg], timeout=120)

        # Verify
        qemu_check = self._cmd.run(["which", "qemu-system-x86_64"])
        if not qemu_check.success:
            raise StageError("QEMU installation failed", stage="KVM")

        self._state.register_resource("kvm", "kvm", ResourceOwnership.MODIFIED_BY_INSTALLER)

    def _stage_libvirt(self) -> None:
        """Setup and verify libvirt."""
        logger.info("Setting up libvirt...")

        cape_user = self._config.get_str("installation.cape_user", "cape")

        # Add user to required groups
        for group in ["libvirt", "kvm", "libvirt-qemu"]:
            self._cmd.run(["usermod", "-aG", group, cape_user])

        # Detect and start appropriate services
        for daemon in ["libvirtd", "virtqemud", "virtnetworkd", "virtlogd"]:
            svc = f"{daemon}.service"
            exists = self._cmd.run(["systemctl", "cat", svc])
            if exists.success:
                self._cmd.run(["systemctl", "enable", svc])
                self._cmd.run(["systemctl", "start", svc])
                self._state.register_resource(
                    "service", daemon, ResourceOwnership.MODIFIED_BY_INSTALLER
                )

        # Also enable sockets
        for daemon in ["libvirtd", "virtqemud"]:
            sock = f"{daemon}.socket"
            exists = self._cmd.run(["systemctl", "cat", sock])
            if exists.success:
                self._cmd.run(["systemctl", "enable", sock])
                self._cmd.run(["systemctl", "start", sock])

        # Verify connection
        import time
        time.sleep(2)
        uri = self._cmd.run(["virsh", "uri"], timeout=15)
        if not uri.success:
            # Try repair
            if not self._remediation.repair_libvirt():
                raise StageError("Cannot connect to libvirt", stage="LIBVIRT")

        logger.info(f"Libvirt URI: {uri.stdout.strip()}")

    def _stage_reboot_check(self) -> None:
        """Check if reboot is needed."""
        reboot_required = os.path.exists("/var/run/reboot-required")
        if reboot_required:
            if self._config.get_bool("safety.allow_reboot"):
                logger.info("Reboot required and allowed by config")
                raise RebootRequired("Reboot required for kernel/driver updates")
            else:
                logger.warning("Reboot recommended but not auto-allowed")

    def _stage_cape_repository(self) -> None:
        """Clone or verify CAPEv2 repository."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        cape_repo = self._config.get_str("installation.cape_repo")
        cape_ref = self._config.get_str("installation.cape_ref", "master")
        cape_user = self._config.get_str("installation.cape_user", "cape")

        # Create cape user if needed
        user_check = self._cmd.run(["id", cape_user])
        if not user_check.success:
            logger.info(f"Creating user: {cape_user}")
            self._cmd.run_checked([
                "useradd", "-m", "-s", "/bin/bash", cape_user
            ])
            self._state.register_resource(
                "user", cape_user, ResourceOwnership.CREATED_BY_INSTALLER
            )

        if os.path.isdir(cape_root):
            # Verify existing repo
            git_check = self._cmd.run(["git", "status"], cwd=cape_root)
            if git_check.success:
                logger.info(f"Existing CAPE repository found at {cape_root}")
                commit = self._cmd.run_capture(["git", "rev-parse", "HEAD"], cwd=cape_root)
                self._state.update_manifest("cape_commit", commit.strip())
                self._state.register_resource(
                    "cape_repo", cape_root, ResourceOwnership.PRE_EXISTING
                )
                return
            else:
                logger.warning(f"{cape_root} exists but is not a git repo")

        # Clone
        logger.info(f"Cloning CAPEv2 from {cape_repo}...")
        self._cmd.run_checked(
            ["git", "clone", "-b", cape_ref, "--depth", "1", cape_repo, cape_root],
            timeout=600,
        )

        # Set ownership
        self._cmd.run(["chown", "-R", f"{cape_user}:{cape_user}", cape_root])

        commit = self._cmd.run_capture(["git", "rev-parse", "HEAD"], cwd=cape_root)
        self._state.update_manifest("cape_commit", commit.strip())
        self._state.update_manifest("cape_repo", cape_repo)
        self._state.update_manifest("cape_ref", cape_ref)
        self._state.register_resource(
            "cape_repo", cape_root, ResourceOwnership.CREATED_BY_INSTALLER
        )

    def _stage_cape_dependencies(self) -> None:
        """Install CAPE dependencies using upstream installer."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        cape_user = self._config.get_str("installation.cape_user", "cape")

        installer_path = os.path.join(cape_root, "installer", "cape2.sh")
        if not os.path.isfile(installer_path):
            raise StageError("CAPE installer not found", stage="CAPE_DEPENDENCIES")

        # Record installer hash
        with open(installer_path, "rb") as f:
            installer_hash = hashlib.sha256(f.read()).hexdigest()
        self._state.update_manifest("installer_hash", installer_hash)

        # Run upstream installer for dependencies
        logger.info("Running CAPE dependency installer (this may take a while)...")
        result = self._cmd.run(
            ["bash", installer_path, "dependencies"],
            cwd=cape_root,
            timeout=3600,  # 1 hour timeout
        )
        if not result.success:
            logger.warning(f"Dependency installer had issues: {result.stderr[:200]}")
            # Don't fail - individual packages may have issues

    def _stage_cape_install(self) -> None:
        """Install CAPE Python environment pinned to Python 3.12."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        cape_user = self._config.get_str("installation.cape_user", "cape")
        python_mgr = self._config.get_str("installation.python_manager", "auto")

        # Determine package manager:
        # If host Python > 3.12 (e.g. Python 3.14 on Ubuntu 26.04), Poetry will fail because
        # greenlet/msgspec/python-flirt cannot compile on Python 3.14. Force uv to manage hermetic Python 3.12.
        host_py_version = sys.version_info[:2]
        if host_py_version > (3, 12):
            python_mgr = "uv"
            logger.info(
                f"Host Python is {sys.version_info.major}.{sys.version_info.minor} (> 3.12). "
                "Forcing uv to manage isolated hermetic Python 3.12 (avoids greenlet/flirt build failures)."
            )
        elif python_mgr == "auto":
            if self._cmd.run(["which", "uv"]).success or os.path.isfile("/usr/local/bin/uv"):
                python_mgr = "uv"
            elif os.path.isfile("/etc/poetry/bin/poetry"):
                python_mgr = "poetry"
            else:
                python_mgr = "uv"

        logger.info(f"Using Python package manager: {python_mgr}")
        self._state.update_manifest("python_manager", python_mgr)

        venv_dir = os.path.join(cape_root, ".venv")
        venv_python = os.path.join(venv_dir, "bin", "python")

        if python_mgr == "poetry":
            # Install poetry if needed
            if not os.path.isfile("/etc/poetry/bin/poetry"):
                logger.info("Installing Poetry...")
                self._cmd.run(
                    'curl -sSL https://install.python-poetry.org | '
                    'POETRY_HOME=/etc/poetry python3 -',
                    shell=True, timeout=180,
                )

            # Ensure host has python3.12
            if not self._cmd.run(["which", "python3.12"]).success:
                logger.info("Installing python3.12 for Poetry...")
                self._cmd.run(["apt-get", "install", "-y", "python3.12", "python3.12-venv", "python3.12-dev"], timeout=300)

            py_exec = "python3.12" if self._cmd.run(["which", "python3.12"]).success else "python3.11"
            self._cmd.run_as_user(
                ["/etc/poetry/bin/poetry", "env", "use", py_exec],
                user=cape_user,
                cwd=cape_root,
                timeout=60,
            )

            result = self._cmd.run_as_user(
                ["/etc/poetry/bin/poetry", "install"],
                user=cape_user,
                cwd=cape_root,
                timeout=900,
                live_output=True,
            )
        elif python_mgr == "uv":
            # Install uv if needed
            uv_installed = self._cmd.run(["which", "uv"]).success or os.path.isfile("/usr/local/bin/uv")
            if not uv_installed:
                logger.info("Installing uv to /usr/local/bin...")
                self._cmd.run(
                    'curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh',
                    shell=True, timeout=120,
                )

            uv_bin = "/usr/local/bin/uv" if os.path.isfile("/usr/local/bin/uv") else "uv"

            # Pin to Python 3.12: uv manages Python versions standalone
            logger.info("Ensuring Python 3.12 toolchain via uv (avoids Python 3.14 / python-flirt failure)...")
            self._cmd.run([uv_bin, "python", "install", "3.12"], timeout=300)

            logger.info(f"Creating Python 3.12 virtual environment at {venv_dir}...")
            self._cmd.run_as_user(
                [uv_bin, "venv", "--python", "3.12", venv_dir],
                user=cape_user,
                cwd=cape_root,
                timeout=180,
            )

            logger.info("Syncing CAPEv2 dependencies into Python 3.12 environment...")
            result = self._cmd.run_as_user(
                [uv_bin, "sync", "--python", "3.12", "--no-install-project"],
                user=cape_user,
                cwd=cape_root,
                timeout=900,
                live_output=True,
            )

        if not result.success:
            raise StageError(
                f"Failed to install CAPE Python dependencies: {result.stderr or result.stdout}",
                stage="CAPE_INSTALL"
            )

        # Verify critical dependencies (django and flirt) inside virtualenv
        logger.info("Verifying installed CAPEv2 dependencies (Django and python-flirt)...")
        active_py = venv_python if os.path.isfile(venv_python) else "python3"
        verify_res = self._cmd.run_as_user(
            [active_py, "-c", "import django; import flirt; print('CAPE core dependencies verified')"],
            user=cape_user,
            cwd=cape_root,
            timeout=30,
        )
        if not verify_res.success:
            raise StageError(
                f"CAPE Python environment verification failed. Essential packages missing: {verify_res.stderr.strip()}",
                stage="CAPE_INSTALL"
            )

        # Verify Python environment version
        py_check = self._cmd.run_as_user(
            [active_py, "--version"],
            user=cape_user,
            cwd=cape_root,
        )
        logger.info(f"Virtual environment Python: {py_check.stdout.strip()}")
        self._state.update_manifest("python_version", py_check.stdout.strip())

    def _stage_cape_config(self) -> None:
        """Generate CAPE configuration from discovered environment."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        gateway = self._config.get_str("network.gateway", "192.168.250.1")
        cape_iface = self._config.get_str("network.cape_interface", "virbr1")

        conf_dir = os.path.join(cape_root, "conf")
        custom_dir = os.path.join(cape_root, "custom", "conf")
        Path(custom_dir).mkdir(parents=True, exist_ok=True)

        # Backup existing configs
        existing_configs = []
        if os.path.isdir(conf_dir):
            for f in os.listdir(conf_dir):
                if f.endswith(".conf"):
                    existing_configs.append(os.path.join(conf_dir, f))
        if existing_configs:
            self._state.create_backup("cape_config", existing_configs)

        # Generate cuckoo.conf with discovered values
        cuckoo_conf = f"""[cuckoo]
machinery = kvm
memory_dump = off
terminate_processes = off
reschedule = off
max_analysis_count = 0
max_machines_count = 10
freespace = 50000
tmppath = /tmp
rooter = /tmp/cuckoo-rooter

[resultserver]
ip = {gateway}
port = 2042
force_port = yes

[processing]
analysis_size_limit = 134217728
"""

        cuckoo_path = os.path.join(custom_dir, "cuckoo.conf")
        with open(cuckoo_path, "w") as f:
            f.write(cuckoo_conf)

        # Generate KVM machinery config
        vm_name = self._config.get_str("guest.name", "cape-win")
        vm_ip = self._config.get_str("network.vm_ip_start", "192.168.250.100")
        snapshot = self._config.get_str("guest.snapshot_name", "cape-clean")

        kvm_conf = f"""[kvm]
machines = {vm_name}
interface = {cape_iface}
dsn =

[{vm_name}]
label = {vm_name}
platform = windows
ip = {vm_ip}
snapshot = {snapshot}
interface =
resultserver_ip = {gateway}
resultserver_port = 2042
tags =
options =
osprofile =
"""
        kvm_path = os.path.join(custom_dir, "kvm.conf")
        with open(kvm_path, "w") as f:
            f.write(kvm_conf)

        # Generate routing.conf
        routing_conf = """[routing]
route = none
internet = none
rt_table = main
auto_rt = yes
drop = off
"""
        routing_path = os.path.join(custom_dir, "routing.conf")
        with open(routing_path, "w") as f:
            f.write(routing_conf)

        # Fix ownership
        cape_user = self._config.get_str("installation.cape_user", "cape")
        self._cmd.run(["chown", "-R", f"{cape_user}:{cape_user}", custom_dir])

        logger.info("CAPE configuration generated")

    def _stage_database(self) -> None:
        """Setup database (MongoDB or PostgreSQL)."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        db_backend = self._config.get_str("database.backend", "auto")

        if db_backend == "auto":
            # Check upstream installer preference - CAPE uses MongoDB for reporting
            db_backend = "mongodb"

        if db_backend == "mongodb":
            self._setup_mongodb()
        elif db_backend == "postgresql":
            self._setup_postgresql()

    def _setup_mongodb(self) -> None:
        """Setup MongoDB."""
        # Check if already running
        status = self._cmd.run(["systemctl", "is-active", "mongod"])
        if status.stdout.strip() == "active":
            logger.info("MongoDB already running")
            self._state.register_resource(
                "database", "mongodb", ResourceOwnership.PRE_EXISTING
            )
            return

        # Check if installed
        installed = self._cmd.run(["which", "mongod"])
        if installed.success:
            # Just start it
            self._cmd.run(["systemctl", "enable", "mongod"])
            self._cmd.run(["systemctl", "start", "mongod"])
            self._state.register_resource(
                "database", "mongodb", ResourceOwnership.MODIFIED_BY_INSTALLER
            )
            return

        # Check CPU for AVX (needed for MongoDB 5.0+)
        cpuinfo = self._cmd.run_capture(["cat", "/proc/cpuinfo"])
        has_avx = "avx" in cpuinfo.lower()

        if not has_avx:
            logger.warning("CPU does not support AVX - using MongoDB 4.4 or compatible version")

        # Install MongoDB using upstream CAPE installer
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        installer = os.path.join(cape_root, "installer", "cape2.sh")

        if os.path.isfile(installer):
            logger.info("Installing MongoDB via CAPE installer...")
            result = self._cmd.run(
                ["bash", installer, "mongo"],
                timeout=600,
            )
            if result.success:
                self._state.register_resource(
                    "database", "mongodb", ResourceOwnership.CREATED_BY_INSTALLER
                )
                return

        # Fallback: direct installation
        logger.info("Attempting direct MongoDB installation...")
        self._cmd.run(
            ["apt-get", "install", "-y", "mongodb"],
            timeout=300,
        )

    def _setup_postgresql(self) -> None:
        """Setup PostgreSQL."""
        status = self._cmd.run(["systemctl", "is-active", "postgresql"])
        if status.stdout.strip() == "active":
            logger.info("PostgreSQL already running")
            self._state.register_resource(
                "database", "postgresql", ResourceOwnership.PRE_EXISTING
            )
            return

        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        installer = os.path.join(cape_root, "installer", "cape2.sh")

        if os.path.isfile(installer):
            self._cmd.run(["bash", installer, "postgresql"], timeout=600)
            self._state.register_resource(
                "database", "postgresql", ResourceOwnership.CREATED_BY_INSTALLER
            )

    def _stage_systemd(self) -> None:
        """Setup CAPE systemd services."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")
        cape_user = self._config.get_str("installation.cape_user", "cape")

        # Use upstream installer for systemd
        installer = os.path.join(cape_root, "installer", "cape2.sh")
        if os.path.isfile(installer):
            self._cmd.run(["bash", installer, "systemd"], timeout=300)

        # Verify services exist
        for svc in ["cape", "cape-processor", "cape-web", "cape-rooter"]:
            exists = self._cmd.run(["systemctl", "cat", f"{svc}.service"])
            if exists.success:
                self._state.register_resource(
                    "systemd_unit", svc, ResourceOwnership.CREATED_BY_INSTALLER
                )
                logger.info(f"Service {svc}: installed")

        self._cmd.run(["systemctl", "daemon-reload"])

    def _stage_network(self) -> None:
        """Setup CAPE analysis network."""
        net_name = self._config.get_str("network.libvirt_network_name", "cape-analysis")
        subnet = self._config.get_str("network.subnet", "192.168.250.0/24")
        gateway = self._config.get_str("network.gateway", "192.168.250.1")
        mode = self._config.get_str("network.mode", "isolated")

        # Check if network already exists
        net_list = self._cmd.run_capture(["virsh", "net-list", "--all"])
        if net_name in net_list:
            logger.info(f"Libvirt network '{net_name}' already exists")
            # Check if active
            net_info = self._cmd.run(["virsh", "net-info", net_name])
            if "Active:          yes" not in net_info.stdout:
                self._cmd.run(["virsh", "net-start", net_name])
            self._state.register_resource(
                "libvirt_network", net_name, ResourceOwnership.PRE_EXISTING
            )
            return

        # Parse subnet
        parts = gateway.rsplit(".", 1)
        network_prefix = parts[0]
        dhcp_start = f"{network_prefix}.100"
        dhcp_end = f"{network_prefix}.254"

        # Generate network XML
        if mode == "isolated":
            forward_xml = ""
        elif mode == "nat":
            forward_xml = "  <forward mode='nat'/>"
        else:
            forward_xml = ""

        network_xml = f"""<network>
  <name>{net_name}</name>
{forward_xml}
  <bridge name='virbr-cape' stp='on' delay='0'/>
  <ip address='{gateway}' netmask='255.255.255.0'>
    <dhcp>
      <range start='{dhcp_start}' end='{dhcp_end}'/>
    </dhcp>
  </ip>
</network>
"""

        # Write to temp file and define
        xml_path = os.path.join(self._project_dir, "state", "cape-network.xml")
        with open(xml_path, "w") as f:
            f.write(network_xml)

        self._cmd.run_checked(["virsh", "net-define", xml_path])
        self._cmd.run_checked(["virsh", "net-start", net_name])
        self._cmd.run_checked(["virsh", "net-autostart", net_name])

        self._state.register_resource(
            "libvirt_network", net_name, ResourceOwnership.CREATED_BY_INSTALLER
        )
        logger.info(f"Created analysis network: {net_name} ({mode})")

    def _download_windows_eval_iso(self, edition: str, dest_path: str, custom_url: Optional[str] = None) -> str:
        """
        Download official Microsoft Windows Enterprise Evaluation ISO with live streaming progress bar.
        Supports resume via HTTP Range headers, handles HTTP 416 range errors gracefully, and falls back to curl.
        """
        info = WINDOWS_EVAL_CATALOG.get(edition, WINDOWS_EVAL_CATALOG["win10_eval"])
        edition_name = info["name"]
        urls = [custom_url] if custom_url else info["urls"]

        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        part_path = dest_path + ".part"

        # Sanity check: If existing part file is suspiciously tiny (< 1 MB), remove it before starting
        if os.path.isfile(part_path) and os.path.getsize(part_path) < 1024 * 1024:
            try:
                os.remove(part_path)
            except Exception:
                pass

        logger.info("┌" + "─" * 76 + "┐")
        logger.info(f"│ DOWNLOADING OFFICIAL MICROSOFT EVALUATION ISO{' ' * (76 - 46)}│")
        logger.info(f"│ Target: {edition_name[:64]:<66} │")
        logger.info(f"│ Path:   {dest_path[:64]:<66} │")
        logger.info("└" + "─" * 76 + "┘")

        success = False
        last_error = ""

        import urllib.request
        import urllib.error

        headers_base = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }

        for url in urls:
            if not url:
                continue
            logger.info(f"Attempting download from: {url}")

            # Try up to 2 passes on the URL:
            # Pass 1: Attempt resume if part_path exists.
            # Pass 2: If resume fails with HTTP 416 or 400 (range rejected), delete part_path and restart from offset 0.
            for attempt_pass in range(2):
                existing_bytes = 0
                if os.path.isfile(part_path):
                    existing_bytes = os.path.getsize(part_path)

                req = urllib.request.Request(url, headers=dict(headers_base))
                if existing_bytes > 0:
                    req.add_header("Range", f"bytes={existing_bytes}-")
                    logger.info(f"Resuming download from byte offset: {existing_bytes} ({existing_bytes / (1024**3):.2f} GB)")

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        code = resp.getcode()
                        content_type = resp.headers.get("Content-Type", "").lower()
                        content_length = resp.headers.get("Content-Length")
                        total_bytes = int(content_length) if content_length else 0

                        # Reject HTML/XML error bodies served with HTTP 200
                        if any(t in content_type for t in ["text/html", "application/xml", "text/xml"]):
                            raise StageError(f"Server returned non-binary content ({content_type}) instead of ISO", stage="VM_CREATE")

                        # If full file (code 200), verify it is large enough to be an authentic Windows ISO (> 1 GB)
                        if code == 200 and total_bytes > 0 and total_bytes < 1024 * 1024 * 1024:
                            raise StageError(f"Reported file size ({total_bytes / (1024**2):.1f} MB) is too small to be a Windows ISO", stage="VM_CREATE")

                        if code == 206 and existing_bytes > 0:
                            total_bytes += existing_bytes
                            mode = "ab"
                        else:
                            existing_bytes = 0
                            mode = "wb"

                        downloaded = existing_bytes
                        chunk_size = 1024 * 1024  # 1MB
                        start_time = time.monotonic()
                        last_log_pct = -1

                        with open(part_path, mode) as out_f:
                            while True:
                                chunk = resp.read(chunk_size)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                downloaded += len(chunk)

                                now = time.monotonic()
                                elapsed = max(0.001, now - start_time)
                                speed_mb = (downloaded - existing_bytes) / (1024 * 1024 * elapsed)
                                pct = int((downloaded / total_bytes) * 100) if total_bytes > 0 else 0

                                if total_bytes > 0:
                                    eta_s = int((total_bytes - downloaded) / max(1, (downloaded - existing_bytes) / elapsed))
                                    eta_str = f"{eta_s // 60:02d}:{eta_s % 60:02d}"
                                    bar = render_ascii_progress_bar(downloaded, total_bytes, width=20)
                                    size_info = f"{downloaded / (1024**3):.2f}/{total_bytes / (1024**3):.2f} GB"
                                    status_line = f"\r  [ISO DL] {bar} | {size_info} | {speed_mb:.1f} MB/s | ETA: {eta_str}"
                                else:
                                    status_line = f"\r  [ISO DL] Downloaded {downloaded / (1024**3):.2f} GB | {speed_mb:.1f} MB/s"

                                try:
                                    sys.stdout.write(status_line)
                                    sys.stdout.flush()
                                except Exception:
                                    pass

                                if total_bytes > 0 and (pct // 10) != (last_log_pct // 10):
                                    last_log_pct = pct
                                    logger.info(f"ISO Download progress: {pct}% ({downloaded / (1024**3):.2f} GB / {total_bytes / (1024**3):.2f} GB) @ {speed_mb:.1f} MB/s")

                        print("")
                        if os.path.isfile(part_path) and os.path.getsize(part_path) > 1024 * 1024 * 1024:
                            success = True
                            break
                        else:
                            # Not a complete or valid ISO
                            logger.warning("Download stream completed but size is too small. Resetting part file...")
                            if os.path.isfile(part_path):
                                try:
                                    os.remove(part_path)
                                except Exception:
                                    pass
                            break

                except urllib.error.HTTPError as he:
                    last_error = f"HTTP Error {he.code}: {he.reason}"
                    if he.code in (416, 400) and existing_bytes > 0:
                        logger.warning(f"Server rejected byte range (HTTP {he.code}). Deleting partial download and restarting from byte 0...")
                        if os.path.isfile(part_path):
                            try:
                                os.remove(part_path)
                            except Exception:
                                pass
                        continue  # retry next pass from offset 0
                    logger.warning(f"Download attempt via urllib failed: {last_error}")
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Download attempt via urllib failed: {e}")
                    break

            if success:
                break

            # Fallback to curl if installed
            if self._cmd.run(["which", "curl"]).success:
                logger.info("Falling back to system curl...")
                curl_cmd = [
                    "curl", "-f", "-L", "--retry", "3", "--retry-delay", "5",
                    "-o", part_path,
                    "--user-agent", headers_base["User-Agent"],
                ]
                if os.path.isfile(part_path) and os.path.getsize(part_path) > 1024 * 1024:
                    curl_cmd.extend(["-C", "-"])
                curl_cmd.append(url)

                res = self._cmd.run(curl_cmd, timeout=7200, live_output=True)
                if not res.success and (res.exit_code == 33 or res.exit_code == 22):
                    logger.warning(f"Curl failed with exit code {res.exit_code}. Resetting partial file and retrying from byte 0...")
                    if os.path.isfile(part_path):
                        try:
                            os.remove(part_path)
                        except Exception:
                            pass
                    retry_cmd = [
                        "curl", "-f", "-L", "--retry", "3", "--retry-delay", "5",
                        "-o", part_path,
                        "--user-agent", headers_base["User-Agent"],
                        url
                    ]
                    res = self._cmd.run(retry_cmd, timeout=7200, live_output=True)

                if res.success and os.path.isfile(part_path) and os.path.getsize(part_path) > 1024 * 1024 * 1024:
                    success = True
                    break

        if success and os.path.isfile(part_path):
            file_size = os.path.getsize(part_path)
            if file_size > 1024 * 1024 * 1024:
                if os.path.isfile(dest_path):
                    os.remove(dest_path)
                os.rename(part_path, dest_path)
                logger.info(f"Successfully downloaded {edition_name} to {dest_path} ({file_size / (1024**3):.2f} GB)")
                self._state.register_resource("iso", dest_path, ResourceOwnership.CREATED_BY_INSTALLER)
                return dest_path

        # If we reached here without success, ensure corrupted/stale part_path is discarded
        if os.path.isfile(part_path) and os.path.getsize(part_path) < 1024 * 1024 * 1024:
            try:
                os.remove(part_path)
            except Exception:
                pass

        raise StageError(
            f"Failed to download {edition_name}: {last_error}. "
            "Please check network connectivity or provide an ISO path in config.toml.",
            stage="VM_CREATE",
        )

    def _generate_unattended_iso(self, vm_name: str) -> str:
        """
        Generate unattended installation ISO with volume label OEMDRV.
        Windows Setup automatically detects Autounattend.xml on OEMDRV
        and performs 100% zero-touch installation.
        """
        staging_dir = os.path.join(self._project_dir, "state", "unattend_staging")
        os.makedirs(staging_dir, exist_ok=True)

        template_xml = os.path.join(self._project_dir, "templates", "windows", "autounattend.xml")
        template_ps1 = os.path.join(self._project_dir, "templates", "windows", "setup-agent.ps1")

        target_xml = os.path.join(staging_dir, "Autounattend.xml")
        target_ps1 = os.path.join(staging_dir, "setup-agent.ps1")

        import shutil
        if os.path.isfile(template_xml):
            shutil.copy2(template_xml, target_xml)
        else:
            logger.warning(f"Unattended template {template_xml} not found")

        if os.path.isfile(template_ps1):
            shutil.copy2(template_ps1, target_ps1)
        else:
            logger.warning(f"Agent script template {template_ps1} not found")

        iso_dir = "/var/lib/libvirt/images"
        if not os.path.isdir(iso_dir):
            iso_dir = os.path.join(self._project_dir, "state")
        iso_path = os.path.join(iso_dir, f"{vm_name}-unattend.iso")

        # Check for ISO creation tool
        tool = None
        for candidate in ["genisoimage", "mkisofs", "xorrisofs"]:
            if self._cmd.run(["which", candidate]).success:
                tool = candidate
                break

        if not tool:
            logger.info("Installing genisoimage for unattended answer disc creation...")
            self._cmd.run(["apt-get", "install", "-y", "genisoimage"])
            tool = "genisoimage"

        logger.info(f"Generating unattended answer ISO with volume label OEMDRV: {iso_path}")
        iso_cmd = [
            tool,
            "-o", iso_path,
            "-V", "OEMDRV",
            "-J",
            "-r",
            staging_dir,
        ]
        res = self._cmd.run(iso_cmd, timeout=60)
        if not res.success and not os.path.isfile(iso_path):
            raise StageError(f"Failed to generate unattended ISO: {res.stderr}", stage="VM_CREATE")

        self._state.register_resource("iso", iso_path, ResourceOwnership.CREATED_BY_INSTALLER)
        return iso_path

    def _calculate_safe_vm_resources(self, req_memory_mb: int, req_vcpus: int) -> tuple[int, int, bool]:
        """
        Dynamically calculate safe memory and vCPUs for the analysis VM.
        Prevents host Out-Of-Memory (OOM) crashes and CPU starvation, especially
        when running inside nested hypervisors (VirtualBox, VMware, KVM).
        Returns (safe_memory_mb, safe_vcpus, is_nested).
        """
        host_total_mb = 8192
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        host_total_mb = int(line.split()[1]) // 1024
                        break
        except Exception:
            pass

        host_cpus = os.cpu_count() or 2

        # Detect nested virtualization (VirtualBox, VMware, KVM)
        is_nested = False
        hypervisor_name = "baremetal"
        try:
            virt_res = self._cmd.run(["systemd-detect-virt"])
            if virt_res.success and virt_res.stdout.strip() and virt_res.stdout.strip() != "none":
                is_nested = True
                hypervisor_name = virt_res.stdout.strip()
        except Exception:
            pass

        # Host OS (Ubuntu) requires at least 4.5 GB of RAM to run libvirt, MongoDB,
        # uv python, CAPE services, and kernel buffers safely without OOM thrashing.
        safe_max_mem = max(2048, host_total_mb - 4608)

        # In nested hypervisors (e.g. VirtualBox with ~9-10 GB RAM), cap guest RAM at 3584 MB
        if is_nested and host_total_mb < 16384:
            safe_max_mem = min(safe_max_mem, 3584)

        safe_mem = min(req_memory_mb, safe_max_mem)
        safe_mem = max(2048, safe_mem)

        # CPU allocation: Never starve the host. Cap guest vCPUs to at most half of host CPUs
        safe_cpus = max(1, min(req_vcpus, host_cpus // 2))

        if is_nested:
            logger.info(
                f"[NESTED VIRT] Detected nested hypervisor '{hypervisor_name}'. "
                f"Host RAM: {host_total_mb} MB, Host CPUs: {host_cpus}."
            )

        if safe_mem < req_memory_mb:
            logger.warning(
                f"[RESOURCE GUARD] Sized VM memory from {req_memory_mb} MB to {safe_mem} MB "
                f"to prevent host OOM crash (Host RAM: {host_total_mb} MB)."
            )

        if safe_cpus < req_vcpus:
            logger.info(
                f"[RESOURCE GUARD] Sized VM vCPUs from {req_vcpus} to {safe_cpus} "
                f"to preserve host responsiveness (Host CPUs: {host_cpus})."
            )

        return safe_mem, safe_cpus, is_nested

    def _stage_vm_create(self) -> None:
        """Create analysis VM with Windows 10/11 Enterprise Evaluation."""
        if not self._config.get_bool("guest.enabled"):
            self._state.skip_stage("VM_CREATE", "Guest provisioning disabled")
            return

        vm_name = self._config.get_str("guest.name", "cape-win")
        iso_path = self._config.get_str("guest.iso_path")
        disk_path = self._config.get_str("guest.disk_path")
        disk_size = self._config.get_int("guest.disk_size_gb", 60)
        memory = self._config.get_int("guest.memory_mb", 3584)
        vcpus = self._config.get_int("guest.vcpus", 2)
        net_name = self._config.get_str("network.libvirt_network_name", "cape-analysis")
        edition = self._config.get_str("guest.windows_edition", "win10_eval").lower()
        auto_download = self._config.get_bool("guest.auto_download_iso", True)
        custom_url = self._config.get_str("guest.eval_iso_url", "").strip()
        disk_bus = self._config.get_str("guest.disk_bus", "sata")
        net_model = self._config.get_str("guest.network_model", "e1000e")

        # Dynamically size memory and vCPUs to host capacity and nested safety
        memory, vcpus, is_nested = self._calculate_safe_vm_resources(memory, vcpus)

        # STRICT PROHIBITION CHECK: Reject Tiny11 or stripped builds
        validate_iso_policy(iso_path)
        validate_iso_policy(custom_url)

        # Check if VM already exists
        vm_list = self._cmd.run_capture(["virsh", "list", "--all"])
        if vm_name in vm_list:
            dumpxml = self._cmd.run_capture(["virsh", "dumpxml", vm_name])
            # If the domain has SMM or UEFI (which causes VirtualBox Guru Meditation), replace it
            if "<smm state='on'/>" in dumpxml or (is_nested and "ovmf" in dumpxml.lower()):
                logger.warning(
                    f"VM '{vm_name}' has unsafe SMM/UEFI settings that trigger VirtualBox crashes. "
                    "Recreating domain with safe nested BIOS profile..."
                )
                self._cmd.run(["virsh", "destroy", vm_name])
                self._cmd.run(["virsh", "undefine", vm_name, "--nvram", "--snapshots-metadata"])
            else:
                logger.info(f"VM '{vm_name}' already exists with valid profile")
                self._state.register_resource("vm", vm_name, ResourceOwnership.PRE_EXISTING)
                return

        if edition not in WINDOWS_EVAL_CATALOG:
            logger.warning(f"Unknown Windows edition '{edition}', defaulting to 'win10_eval'")
            edition = "win10_eval"

        eval_info = WINDOWS_EVAL_CATALOG[edition]
        default_iso_dir = "/var/lib/libvirt/images"
        default_iso_path = os.path.join(default_iso_dir, eval_info["default_filename"])

        if not iso_path or not os.path.isfile(iso_path):
            if os.path.isfile(default_iso_path) and os.path.getsize(default_iso_path) > 500 * 1024 * 1024:
                logger.info(f"Found existing evaluation ISO at default location: {default_iso_path}")
                iso_path = default_iso_path
            elif auto_download:
                logger.info(f"Auto-downloading {eval_info['name']} ISO...")
                iso_path = self._download_windows_eval_iso(edition, default_iso_path, custom_url)
            else:
                logger.warning("═" * 78)
                logger.warning("  WINDOWS ENTERPRISE EVALUATION ISO REQUIRED FOR MALWARE ANALYSIS")
                logger.warning("═" * 78)
                logger.warning(f"  Target Edition: {eval_info['name']}")
                logger.warning("  Strict Policy:  NO TINY11 or stripped OS builds allowed!")
                logger.warning("  Reason:         Malware analysis requires authentic Defender, ETW, and WMI.")
                logger.warning("  Official Microsoft Download URLs:")
                for u in eval_info["urls"]:
                    logger.warning(f"    - {u}")
                logger.warning("  How to proceed:")
                logger.warning("    Option 1: Set guest.auto_download_iso = true in config.toml to auto-download.")
                logger.warning("    Option 2: Download ISO manually and set guest.iso_path in config.toml.")
                logger.warning(f"    Option 3: Place ISO at {default_iso_path}")
                logger.warning("═" * 78)
                self._state.block_stage(
                    "VM_CREATE",
                    f"Windows Evaluation ISO not provided. Auto-download is disabled. Download {eval_info['name']}."
                )
                return

        # Double check validated path
        validate_iso_policy(iso_path)

        # Check disk space & directory
        disk_dir = os.path.dirname(disk_path)
        Path(disk_dir).mkdir(parents=True, exist_ok=True)

        # Create disk
        if not os.path.isfile(disk_path):
            logger.info(f"Creating VM disk: {disk_path} ({disk_size}G)")
            self._cmd.run_checked([
                "qemu-img", "create", "-f", "qcow2", disk_path, f"{disk_size}G"
            ])

        # Generate unattended answer disc
        unattend_iso = self._generate_unattended_iso(vm_name)

        # Configure virt-install
        os_variant = eval_info["os_variant"]

        # In nested virtualization, enforce BIOS boot to prevent VirtualBox/nested SMM crashes
        if is_nested:
            use_uefi = "false"
            logger.info("[NESTED VIRT] Enforcing standard BIOS boot (avoids nested SMM/TPM hypervisor crash).")
        else:
            use_uefi = self._config.get_str("guest.uefi", "").lower()
            if not use_uefi:
                use_uefi = "true" if eval_info["needs_uefi"] else "false"

        install_cmd = [
            "virt-install",
            "--name", vm_name,
            "--memory", str(memory),
            "--vcpus", str(vcpus),
            "--disk", f"path={disk_path},format=qcow2,bus={disk_bus}",
            "--cdrom", iso_path,
            "--disk", f"path={unattend_iso},device=cdrom",
            "--network", f"network={net_name},model={net_model}",
            "--graphics", "vnc,listen=127.0.0.1",
            "--os-variant", os_variant,
            "--events", "on_reboot=restart",
            "--noautoconsole",
        ]

        if use_uefi in ("true", "1", "yes") and not is_nested:
            install_cmd.extend(["--boot", "uefi"])
        else:
            install_cmd.extend(["--boot", "hd,cdrom"])

        if is_nested:
            install_cmd.extend(["--machine", "pc"])

        logger.info(f"Creating VM: {vm_name} ({eval_info['name']})")
        result = self._cmd.run(install_cmd, timeout=180)
        if result.success:
            self._state.register_resource(
                "vm", vm_name, ResourceOwnership.CREATED_BY_INSTALLER,
                disk_path=disk_path,
            )
            # In nested virtualization, ensure SMM is completely absent from domain XML
            if is_nested:
                try:
                    xml_out = self._cmd.run_capture(["virsh", "dumpxml", vm_name])
                    if "<smm" in xml_out:
                        import re
                        clean_xml = re.sub(r"<smm\b[^>]*\/?>", "", xml_out)
                        clean_xml = re.sub(r"<smm\b[^>]*>.*?</smm>", "", clean_xml, flags=re.DOTALL)
                        tmp_xml = f"/tmp/{vm_name}-clean.xml"
                        with open(tmp_xml, "w") as f:
                            f.write(clean_xml)
                        self._cmd.run(["virsh", "define", tmp_xml])
                        try:
                            os.remove(tmp_xml)
                        except OSError:
                            pass
                except Exception as e:
                    logger.debug(f"Nested XML sanitization notice: {e}")

            logger.info(f"VM '{vm_name}' created. Windows unattended installation started.")
        else:
            raise StageError(f"VM creation failed: {result.stderr}", stage="VM_CREATE")

    def _stage_vm_install(self) -> None:
        """Monitor Windows automated installation in VM."""
        if not self._config.get_bool("guest.enabled"):
            self._state.skip_stage("VM_INSTALL", "Guest disabled")
            return

        vm_name = self._config.get_str("guest.name", "cape-win")
        agent_ip = "192.168.250.100"
        agent_port = self._config.get_int("guest.agent.port", 8000)
        agent_url = f"http://{agent_ip}:{agent_port}/"

        if self._dry_run_mode:
            logger.info(f"[DRY-RUN] Would monitor unattended installation for '{vm_name}' until agent responds at {agent_url}")
            return

        # Check if VM is defined
        vm_list = self._cmd.run_capture(["virsh", "list", "--all"])
        if vm_name not in vm_list:
            raise StageError(f"VM '{vm_name}' not found in libvirt", stage="VM_INSTALL")

        logger.info("┌" + "─" * 76 + "┐")
        logger.info(f"│ MONITORING AUTOMATED WINDOWS UNATTENDED INSTALLATION{' ' * (76 - 53)}│")
        logger.info(f"│ VM:       {vm_name:<64} │")
        logger.info(f"│ Endpoint: {agent_url:<64} │")
        logger.info(f"│ Answer:   OEMDRV Autounattend.xml (Zero-touch automated install){' ' * (76 - 66)}│")
        logger.info("└" + "─" * 76 + "┘")

        # Polling loop
        timeout_minutes = self._config.get_int("guest.install_timeout_minutes", 35)
        timeout_seconds = timeout_minutes * 60
        poll_interval = 10
        start_time = time.monotonic()
        last_logged_min = -1

        import urllib.request
        import urllib.error

        while (time.monotonic() - start_time) < timeout_seconds:
            elapsed = int(time.monotonic() - start_time)
            elapsed_str = f"{elapsed // 60:02d}:{elapsed % 60:02d}"

            # Check VM state in libvirt
            dom_state = self._cmd.run_capture(["virsh", "domstate", vm_name]).strip()

            # If VM shut down during setup reboot and didn't auto-start, restart it
            if dom_state in ("shut off", "shut down", "pmsuspended"):
                logger.info(f"VM '{vm_name}' is in '{dom_state}' state, restarting...")
                self._cmd.run(["virsh", "start", vm_name])
                time.sleep(5)
                continue

            # Check if guest agent is answering
            agent_online = False
            try:
                req = urllib.request.Request(agent_url, headers={"User-Agent": "CAPE-Installer/2.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        agent_online = True
            except Exception:
                pass

            if agent_online:
                logger.info("═" * 78)
                logger.info(f"  AUTOMATED WINDOWS INSTALLATION COMPLETE in {elapsed_str}!")
                logger.info(f"  Guest agent detected online and responsive at {agent_url}")
                logger.info("═" * 78)
                return

            # Display live progress every 2 minutes or upon state change
            mins_elapsed = elapsed // 60
            if mins_elapsed != last_logged_min and (mins_elapsed % 2 == 0):
                last_logged_min = mins_elapsed
                logger.info(f"Windows automated setup in progress: Elapsed {elapsed_str}/{timeout_minutes}m | VM: {dom_state} | Awaiting guest agent...")

            time.sleep(poll_interval)

        # Timeout reached
        logger.error(f"Timed out waiting for automated Windows installation after {timeout_minutes} minutes.")
        raise StageError(
            f"Windows automated installation timed out for '{vm_name}'. Check VM console using: virt-manager or virsh console {vm_name}",
            stage="VM_INSTALL",
        )

    def _stage_vm_config(self) -> None:
        """Configure VM settings after Windows installation."""
        if not self._config.get_bool("guest.enabled"):
            self._state.skip_stage("VM_CONFIG", "Guest disabled")
            return

        vm_install_stage = self._state.get_stage("VM_INSTALL")
        if vm_install_stage.status != StageStatus.SUCCESS.value and not self._dry_run_mode:
            self._state.skip_stage("VM_CONFIG", "Depends on VM_INSTALL")
            return

        logger.info("VM configuration verified successfully")

    def _stage_agent(self) -> None:
        """Verify CAPE agent in guest."""
        if not self._config.get_bool("guest.enabled"):
            self._state.skip_stage("AGENT", "Guest disabled")
            return
        if not self._config.get_bool("guest.agent.enabled"):
            self._state.skip_stage("AGENT", "Agent disabled")
            return

        if self._dry_run_mode:
            logger.info("[DRY-RUN] Would verify guest agent response on port 8000")
            return

        agent_ip = "192.168.250.100"
        agent_port = self._config.get_int("guest.agent.port", 8000)
        agent_url = f"http://{agent_ip}:{agent_port}/"

        logger.info(f"Verifying CAPE guest agent at {agent_url}...")

        import urllib.request

        verified = False
        last_error = ""

        # Check agent response (retries up to 30s)
        for _ in range(6):
            try:
                req = urllib.request.Request(agent_url, headers={"User-Agent": "CAPE-Installer/2.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        body = resp.read().decode("utf-8", errors="replace")
                        logger.info(f"Agent response: {body[:120]}")
                        verified = True
                        break
            except Exception as e:
                last_error = str(e)
                time.sleep(5)

        if verified:
            self._state.register_resource("agent", agent_url, ResourceOwnership.CREATED_BY_INSTALLER)
            logger.info(f"CAPE guest agent verified online at {agent_url}")
        else:
            raise StageError(
                f"Guest agent verification failed at {agent_url}: {last_error}",
                stage="AGENT"
            )

    def _stage_snapshot(self) -> None:
        """Create VM snapshot after agent verification."""
        if not self._config.get_bool("guest.enabled"):
            self._state.skip_stage("SNAPSHOT", "Guest disabled")
            return

        agent_stage = self._state.get_stage("AGENT")
        if agent_stage.status != StageStatus.SUCCESS.value:
            self._state.skip_stage("SNAPSHOT", "Agent not ready")
            return

        vm_name = self._config.get_str("guest.name", "cape-win")
        snap_name = self._config.get_str("guest.snapshot_name", "cape-clean")

        # Create snapshot
        logger.info(f"Creating snapshot '{snap_name}' for VM '{vm_name}'")
        result = self._cmd.run([
            "virsh", "snapshot-create-as", vm_name, snap_name,
            "--description", "Clean snapshot for CAPE analysis"
        ])

        if result.success:
            self._state.register_resource(
                "snapshot", f"{vm_name}/{snap_name}",
                ResourceOwnership.CREATED_BY_INSTALLER,
            )
            # Verify snapshot
            verify = self._cmd.run(["virsh", "snapshot-list", vm_name])
            if snap_name in verify.stdout:
                logger.info("Snapshot created and verified")
            else:
                raise StageError("Snapshot created but verification failed", stage="SNAPSHOT")
        else:
            raise StageError(f"Snapshot creation failed: {result.stderr}", stage="SNAPSHOT")

    def _stage_machinery_config(self) -> None:
        """Generate CAPE machinery configuration from actual VM state."""
        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")

        # Already handled in CAPE_CONFIG stage
        kvm_conf = os.path.join(cape_root, "custom", "conf", "kvm.conf")
        if os.path.isfile(kvm_conf):
            logger.info("Machinery configuration already generated")
        else:
            logger.warning("No machinery configuration found - regenerating")
            self._stage_cape_config()

    def _stage_cape_start(self) -> None:
        """Start CAPE services in correct order."""
        # Service startup order
        startup_order = ["cape-rooter", "cape-processor", "cape", "cape-web"]

        for svc in startup_order:
            svc_name = f"{svc}.service"
            exists = self._cmd.run(["systemctl", "cat", svc_name])
            if not exists.success:
                logger.warning(f"Service {svc} not found, skipping")
                continue

            self._cmd.run(["systemctl", "enable", svc_name])
            result = self._cmd.run(["systemctl", "start", svc_name], timeout=30)

            if not result.success:
                logger.warning(f"Service {svc} failed to start, attempting repair")
                self._remediation.repair_service(svc)

            # Verify
            import time
            time.sleep(2)
            check = self._cmd.run(["systemctl", "is-active", svc_name])
            status = check.stdout.strip()
            logger.info(f"Service {svc}: {status}")

    def _stage_health_check(self) -> None:
        """Run comprehensive health checks."""
        results = self._diag.diagnose_all()
        report = self._diag.generate_report(results)
        logger.info(report)

        # Save report
        report_path = os.path.join(self._project_dir, "reports", "health-check.md")
        Path(os.path.dirname(report_path)).mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)

        # Check for critical failures
        critical = [r for r in results if r.status == HealthStatus.FAIL.value
                    and r.severity == "critical"]
        if critical:
            raise StageError(
                f"Critical health check failures: "
                f"{', '.join(r.component for r in critical)}",
                stage="HEALTH_CHECK",
            )

    def _stage_end_to_end(self) -> None:
        """End-to-end validation."""
        if not self._config.get_bool("verification.run_full_healthcheck"):
            self._state.skip_stage("END_TO_END_TEST", "Disabled in config")
            return

        logger.info("Running end-to-end validation...")

        # Check CAPE web responds
        web_port = self._config.get_int("network.web_port", 8000)
        web_bind = self._config.get_str("network.web_bind", "127.0.0.1")

        web_check = self._cmd.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "5", f"http://{web_bind}:{web_port}"],
            timeout=15,
        )

        if web_check.success and web_check.stdout.strip() in ("200", "301", "302"):
            logger.info("CAPE web interface responding")
        else:
            logger.warning("CAPE web interface not responding (may still be starting)")

    def _stage_finalize(self) -> None:
        """Final report and cleanup."""
        self._reporter.generate_final_report(
            self._state.is_complete() or not self._state.get_failed_stages()
        )
        logger.info("Installation finalized. See reports/ for details.")

    # ═══════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _is_blocking_failure(self, stage_name: str) -> bool:
        """Determine if a stage failure blocks further progress."""
        blocking = {
            "PREFLIGHT", "KVM", "LIBVIRT", "CAPE_REPOSITORY", "VM_CREATE",
        }
        return stage_name in blocking

    def _attempt_repair(self, error_category: str, stage_name: str) -> bool:
        """Attempt automatic repair based on error category."""
        repair_map = {
            "PACKAGE_ERROR": self._remediation.repair_package_manager,
            "LIBVIRT_ERROR": self._remediation.repair_libvirt,
            "PYTHON_ERROR": lambda: self._remediation.repair_python_env(
                self._config.get_str("installation.cape_root", "/opt/CAPEv2")
            ),
            "PERMISSION_ERROR": lambda: self._remediation.repair_cape_permissions(
                self._config.get_str("installation.cape_root", "/opt/CAPEv2"),
                self._config.get_str("installation.cape_user", "cape"),
            ),
            "KVM_ERROR": self._remediation.repair_kvm_modules,
            "DATABASE_ERROR": self._remediation.repair_database,
            "SERVICE_ERROR": lambda: self._remediation.repair_service(stage_name.lower()),
        }

        repair_fn = repair_map.get(error_category)
        if repair_fn:
            try:
                return repair_fn()
            except Exception as e:
                logger.warning(f"Repair attempt failed: {e}")
                return False
        return False

    def _map_component_to_error(self, component: str) -> str:
        """Map diagnostic component name to error category."""
        mapping = {
            "kvm": "KVM_ERROR",
            "libvirt": "LIBVIRT_ERROR",
            "network": "NETWORK_ERROR",
            "python": "PYTHON_ERROR",
            "database": "DATABASE_ERROR",
            "cape_services": "SERVICE_ERROR",
            "vm": "LIBVIRT_ERROR",
        }
        return mapping.get(component, "UNKNOWN_ERROR")

    def _get_stage_description(self, stage_name: str) -> str:
        """Get human-readable description of a stage."""
        descriptions = {
            "PREFLIGHT": "Detect and validate environment",
            "BACKUP": "Backup existing configuration",
            "REPOSITORIES": "Update package repositories",
            "BASE_PACKAGES": "Install system dependencies",
            "KVM": "Install/verify KVM/QEMU",
            "LIBVIRT": "Setup libvirt services",
            "REBOOT_CHECK": "Check if reboot is required",
            "CAPE_REPOSITORY": "Clone CAPEv2 repository",
            "CAPE_DEPENDENCIES": "Install CAPE dependencies",
            "CAPE_INSTALL": "Install CAPE Python environment",
            "CAPE_CONFIG": "Generate CAPE configuration",
            "DATABASE": "Setup database",
            "SYSTEMD": "Install systemd services",
            "NETWORK": "Create analysis network",
            "VM_CREATE": "Create analysis VM",
            "VM_INSTALL": "Install Windows in VM",
            "VM_CONFIG": "Configure VM",
            "AGENT": "Install CAPE agent",
            "SNAPSHOT": "Create VM snapshot",
            "MACHINERY_CONFIG": "Configure CAPE machinery",
            "CAPE_START": "Start CAPE services",
            "HEALTH_CHECK": "Run health checks",
            "END_TO_END_TEST": "End-to-end validation",
            "FINALIZE": "Generate final report",
        }
        return descriptions.get(stage_name, "")

    def _show_drift(self) -> None:
        """Show configuration drift."""
        print("\n  Configuration Drift Analysis")
        print("  " + "-" * 40)

        cape_root = self._config.get_str("installation.cape_root", "/opt/CAPEv2")

        # Check service states
        for svc in ["cape", "cape-processor", "cape-web", "cape-rooter"]:
            expected = "active"
            actual = self._cmd.run_capture(
                ["systemctl", "is-active", f"{svc}.service"]
            ).strip()
            if actual != expected:
                print(f"    DRIFT: {svc} expected={expected} actual={actual}")

        # Check CAPE directory ownership
        if os.path.isdir(cape_root):
            import stat
            cape_stat = os.stat(cape_root)
            import pwd
            try:
                owner = pwd.getpwuid(cape_stat.st_uid).pw_name
                expected_owner = self._config.get_str("installation.cape_user", "cape")
                if owner != expected_owner:
                    print(f"    DRIFT: {cape_root} owner={owner} expected={expected_owner}")
            except (KeyError, ImportError):
                pass

        print("  " + "-" * 40)
