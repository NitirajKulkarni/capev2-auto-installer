"""
Report generator for CAPEv2 Automated Installer.

Produces human-readable Markdown and machine-readable JSON reports
for final status, manual interventions, and diagnostics.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cape_auto.state import StateManager, StageStatus, HealthStatus, INSTALLATION_STAGES
from cape_auto.config import Config
from cape_auto.logging_setup import get_logger

logger = get_logger("reporting")


class ReportGenerator:
    """Generates installation reports in Markdown and JSON formats."""

    def __init__(self, reports_dir: str, state: StateManager, config: Config):
        self._reports_dir = reports_dir
        self._state = state
        self._config = config
        Path(reports_dir).mkdir(parents=True, exist_ok=True)

    def generate_final_report(self, overall_success: bool) -> None:
        """Generate the final installation report."""
        manifest = self._state.get_manifest()
        summary = self._state.get_summary()

        # Determine overall result
        failed = self._state.get_failed_stages()
        blocked = [
            name for name in INSTALLATION_STAGES
            if self._state.get_stage(name).status == StageStatus.BLOCKED.value
        ]

        if overall_success and not failed:
            result = "SUCCESS"
        elif failed and not all(self._is_critical_stage(s) for s in failed):
            result = "PARTIAL SUCCESS"
        else:
            result = "FAILED"

        # Generate Markdown
        md_lines = [
            "# CAPEv2 Installation Report",
            "",
            f"**Result: {result}**",
            "",
            f"- Installation ID: `{manifest.get('installation_id', 'N/A')}`",
            f"- Timestamp: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## System Information",
            "",
            f"| Property | Value |",
            f"|----------|-------|",
            f"| Ubuntu | {manifest.get('ubuntu_version', 'N/A')} ({manifest.get('ubuntu_codename', '')}) |",
            f"| Kernel | {manifest.get('kernel', 'N/A')} |",
            f"| Architecture | {manifest.get('architecture', 'N/A')} |",
            f"| CPU | {manifest.get('cpu_model', 'N/A')} |",
            f"| RAM | {manifest.get('ram_gb', 'N/A')} GB |",
            f"| Compatibility | {manifest.get('compatibility_class', 'N/A')} |",
            "",
            "## CAPE Information",
            "",
            f"| Property | Value |",
            f"|----------|-------|",
            f"| Repository | {manifest.get('cape_repo', 'N/A')} |",
            f"| Commit | `{manifest.get('cape_commit', 'N/A')[:12]}` |",
            f"| Python | {manifest.get('python_version', 'N/A')} |",
            f"| Package Manager | {manifest.get('python_manager', 'N/A')} |",
            "",
            "## Stage Results",
            "",
            "| Stage | Status | Notes |",
            "|-------|--------|-------|",
        ]

        status_icons = {
            "success": "[PASS]",
            "failed": "[FAIL]",
            "pending": "[PENDING]",
            "running": "[RUNNING]",
            "skipped": "[SKIP]",
            "blocked": "[BLOCKED]",
        }

        for name in INSTALLATION_STAGES:
            info = summary.get(name, {})
            status = info.get("status", "unknown")
            icon = status_icons.get(status, status)
            error = info.get("error", "")
            notes = error[:80] if error else ""
            md_lines.append(f"| {name} | {icon} | {notes} |")

        md_lines.extend([
            "",
            "## Summary",
            "",
        ])

        if failed:
            md_lines.append(f"### Failed Stages ({len(failed)})")
            for stage_name in failed:
                stage = self._state.get_stage(stage_name)
                md_lines.extend([
                    f"- **{stage_name}**: {stage.error_message}",
                    f"  - Attempts: {stage.attempt}",
                    f"  - Repairs tried: {', '.join(stage.repairs_attempted) or 'none'}",
                ])

        if blocked:
            md_lines.append(f"\n### Blocked Stages ({len(blocked)})")
            for stage_name in blocked:
                stage = self._state.get_stage(stage_name)
                md_lines.append(f"- **{stage_name}**: {stage.error_message}")

        md_lines.extend([
            "",
            "## Next Steps",
            "",
        ])

        if result == "SUCCESS":
            md_lines.extend([
                "Installation complete. CAPEv2 should be operational.",
                "",
                "- Check status: `sudo ./status.sh`",
                "- Run diagnostics: `sudo ./diagnose.sh`",
                f"- Web interface: http://{self._config.get_str('network.web_bind', '127.0.0.1')}:{self._config.get_int('network.web_port', 8000)}",
            ])
        elif result == "PARTIAL SUCCESS":
            md_lines.extend([
                "Some components need attention. The host installation is functional",
                "but some features may be unavailable.",
                "",
                "- Resume failed stages: `sudo ./install.sh --resume`",
                "- Run repair: `sudo ./repair.sh`",
                "- Check diagnostics: `sudo ./diagnose.sh`",
            ])
        else:
            md_lines.extend([
                "Installation encountered critical failures.",
                "",
                "- Run diagnostics: `sudo ./diagnose.sh`",
                "- Attempt repair: `sudo ./repair.sh`",
                "- Resume: `sudo ./install.sh --resume`",
                "- Reset and retry: `sudo ./install.sh --reset-failed`",
            ])

        # Write Markdown
        md_path = os.path.join(self._reports_dir, "final-report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        # Write JSON
        json_data = {
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "manifest": manifest,
            "stages": summary,
            "failed_stages": failed,
            "blocked_stages": blocked,
        }
        json_path = os.path.join(self._reports_dir, "final-report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        logger.info(f"Final report: {md_path}")

    def generate_manual_intervention_report(
        self, stage: str, problem: str, evidence_path: str = ""
    ) -> str:
        """Generate a manual intervention report."""
        report = f"""# Manual Intervention Required

## Problem
{problem}

## Stage
{stage}

## What Failed
The automated installer cannot safely resolve this issue.

## Evidence
See logs/ directory for detailed command output.

## What Was Already Attempted
Check state/state.json for repair attempts on this stage.

## What Must Be Done Manually
Refer to the specific error message above for required action.

## How to Resume
After resolving the issue manually:
```bash
sudo ./install.sh --resume
```

## How to Verify
```bash
sudo ./install.sh --diagnose
```
"""
        report_path = os.path.join(self._reports_dir, "manual-intervention.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"Manual intervention report: {report_path}")
        return report_path

    def _is_critical_stage(self, stage_name: str) -> bool:
        """Check if a stage is critical for basic operation."""
        critical = {"PREFLIGHT", "KVM", "LIBVIRT", "CAPE_REPOSITORY",
                    "CAPE_INSTALL", "CAPE_CONFIG"}
        return stage_name in critical
