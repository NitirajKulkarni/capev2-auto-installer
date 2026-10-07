"""
State machine and checkpoint management for CAPEv2 Automated Installer.

Tracks installation stages, enables resume after reboot/interruption,
manages resource ownership registry, and provides rollback metadata.
"""
import json
import os
import hashlib
import shutil
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any

from cape_auto.logging_setup import get_logger

logger = get_logger("state")


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ResourceOwnership(str, Enum):
    PRE_EXISTING = "pre_existing"
    CREATED_BY_INSTALLER = "created_by_installer"
    MODIFIED_BY_INSTALLER = "modified_by_installer"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# Ordered list of installation stages
INSTALLATION_STAGES = [
    "PREFLIGHT",
    "BACKUP",
    "REPOSITORIES",
    "BASE_PACKAGES",
    "KVM",
    "LIBVIRT",
    "REBOOT_CHECK",
    "CAPE_REPOSITORY",
    "CAPE_DEPENDENCIES",
    "CAPE_INSTALL",
    "CAPE_CONFIG",
    "DATABASE",
    "SYSTEMD",
    "NETWORK",
    "VM_CREATE",
    "VM_INSTALL",
    "VM_CONFIG",
    "AGENT",
    "SNAPSHOT",
    "MACHINERY_CONFIG",
    "CAPE_START",
    "HEALTH_CHECK",
    "END_TO_END_TEST",
    "FINALIZE",
]


@dataclass
class StageState:
    name: str
    status: str = StageStatus.PENDING.value
    attempt: int = 0
    timestamp_start: str = ""
    timestamp_end: str = ""
    error_message: str = ""
    verification_passed: Optional[bool] = None
    repairs_attempted: list[str] = field(default_factory=list)


@dataclass
class ResourceRecord:
    resource_type: str  # e.g., "libvirt_network", "vm", "systemd_unit"
    name: str
    ownership: str = ResourceOwnership.UNKNOWN.value
    created_at: str = ""
    details: dict = field(default_factory=dict)


class StateManager:
    """
    Manages installation state, checkpoints, and resource ownership.

    State is persisted to state/state.json so installation can resume
    after reboot, SSH disconnect, or crash.
    """

    def __init__(self, state_dir: str, backup_dir: str):
        self._state_dir = state_dir
        self._backup_dir = backup_dir
        self._state_file = os.path.join(state_dir, "state.json")
        self._resources_file = os.path.join(state_dir, "resources.json")
        self._manifest_file = os.path.join(state_dir, "installation-manifest.json")
        self._checkpoint_dir = os.path.join(state_dir, "checkpoints")

        Path(state_dir).mkdir(parents=True, exist_ok=True)
        Path(self._checkpoint_dir).mkdir(parents=True, exist_ok=True)
        Path(backup_dir).mkdir(parents=True, exist_ok=True)

        self._stages: dict[str, StageState] = {}
        self._resources: list[ResourceRecord] = []
        self._manifest: dict[str, Any] = {}
        self._installation_id: str = ""

        self._load()

    def _load(self) -> None:
        """Load existing state from disk."""
        if os.path.isfile(self._state_file):
            try:
                with open(self._state_file, "r") as f:
                    data = json.load(f)
                self._installation_id = data.get("installation_id", "")
                for name, stage_data in data.get("stages", {}).items():
                    self._stages[name] = StageState(**stage_data)
                logger.info(f"Loaded existing state (ID: {self._installation_id[:12]}...)")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Could not load state file: {e}")
                self._stages = {}

        if os.path.isfile(self._resources_file):
            try:
                with open(self._resources_file, "r") as f:
                    data = json.load(f)
                self._resources = [ResourceRecord(**r) for r in data.get("resources", [])]
            except (json.JSONDecodeError, TypeError):
                self._resources = []

        if os.path.isfile(self._manifest_file):
            try:
                with open(self._manifest_file, "r") as f:
                    self._manifest = json.load(f)
            except (json.JSONDecodeError, TypeError):
                self._manifest = {}

        # Initialize stages if empty
        if not self._stages:
            self._installation_id = hashlib.sha256(
                datetime.now(timezone.utc).isoformat().encode()
            ).hexdigest()[:24]
            for stage_name in INSTALLATION_STAGES:
                self._stages[stage_name] = StageState(name=stage_name)
            self._save()

    def _save(self) -> None:
        """Persist state to disk atomically."""
        state_data = {
            "installation_id": self._installation_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "stages": {name: asdict(stage) for name, stage in self._stages.items()},
        }
        tmp_path = self._state_file + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(state_data, f, indent=2)
        os.replace(tmp_path, self._state_file)

    def _save_resources(self) -> None:
        """Persist resource registry to disk."""
        data = {"resources": [asdict(r) for r in self._resources]}
        tmp_path = self._resources_file + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self._resources_file)

    # ─── Stage management ────────────────────────────────────────────────

    def get_stage(self, name: str) -> StageState:
        if name not in self._stages:
            self._stages[name] = StageState(name=name)
        return self._stages[name]

    def start_stage(self, name: str) -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.RUNNING.value
        stage.attempt += 1
        stage.timestamp_start = datetime.now(timezone.utc).isoformat()
        stage.error_message = ""
        self._save()
        logger.info(f"Stage {name}: STARTED (attempt {stage.attempt})")

    def complete_stage(self, name: str, verified: bool = True) -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.SUCCESS.value
        stage.timestamp_end = datetime.now(timezone.utc).isoformat()
        stage.verification_passed = verified
        self._save()
        logger.info(f"Stage {name}: SUCCESS")

    def fail_stage(self, name: str, error: str) -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.FAILED.value
        stage.timestamp_end = datetime.now(timezone.utc).isoformat()
        stage.error_message = error
        self._save()
        logger.error(f"Stage {name}: FAILED - {error}")

    def skip_stage(self, name: str, reason: str = "") -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.SKIPPED.value
        stage.error_message = reason
        self._save()
        logger.info(f"Stage {name}: SKIPPED - {reason}")

    def block_stage(self, name: str, reason: str = "") -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.BLOCKED.value
        stage.error_message = reason
        self._save()
        logger.warning(f"Stage {name}: BLOCKED - {reason}")

    def reset_stage(self, name: str) -> None:
        stage = self.get_stage(name)
        stage.status = StageStatus.PENDING.value
        stage.attempt = 0
        stage.error_message = ""
        stage.verification_passed = None
        stage.repairs_attempted = []
        self._save()

    def add_repair_attempt(self, stage_name: str, repair_id: str) -> None:
        stage = self.get_stage(stage_name)
        stage.repairs_attempted.append(repair_id)
        self._save()

    def get_resume_stage(self) -> Optional[str]:
        """Determine which stage to resume from."""
        for name in INSTALLATION_STAGES:
            stage = self.get_stage(name)
            if stage.status in (StageStatus.PENDING.value, StageStatus.RUNNING.value,
                               StageStatus.FAILED.value):
                return name
        return None

    def get_stage_from(self, stage_name: str) -> Optional[int]:
        """Get index of a stage by name."""
        try:
            return INSTALLATION_STAGES.index(stage_name)
        except ValueError:
            return None

    def is_complete(self) -> bool:
        """Check if all stages are either SUCCESS or SKIPPED."""
        for name in INSTALLATION_STAGES:
            stage = self.get_stage(name)
            if stage.status not in (StageStatus.SUCCESS.value, StageStatus.SKIPPED.value):
                return False
        return True

    def get_failed_stages(self) -> list[str]:
        """Get list of failed stage names."""
        return [
            name for name in INSTALLATION_STAGES
            if self.get_stage(name).status == StageStatus.FAILED.value
        ]

    # ─── Resource ownership ──────────────────────────────────────────────

    def register_resource(
        self,
        resource_type: str,
        name: str,
        ownership: ResourceOwnership = ResourceOwnership.CREATED_BY_INSTALLER,
        **details,
    ) -> None:
        """Register a resource and its ownership."""
        record = ResourceRecord(
            resource_type=resource_type,
            name=name,
            ownership=ownership.value,
            created_at=datetime.now(timezone.utc).isoformat(),
            details=details,
        )
        # Update if exists, else append
        for i, r in enumerate(self._resources):
            if r.resource_type == resource_type and r.name == name:
                self._resources[i] = record
                self._save_resources()
                return
        self._resources.append(record)
        self._save_resources()
        logger.debug(f"Registered resource: {resource_type}/{name} ({ownership.value})")

    def get_resources(self, resource_type: Optional[str] = None) -> list[ResourceRecord]:
        """Get registered resources, optionally filtered by type."""
        if resource_type:
            return [r for r in self._resources if r.resource_type == resource_type]
        return list(self._resources)

    def is_owned_by_us(self, resource_type: str, name: str) -> bool:
        """Check if a resource was created or modified by this installer."""
        for r in self._resources:
            if r.resource_type == resource_type and r.name == name:
                return r.ownership in (
                    ResourceOwnership.CREATED_BY_INSTALLER.value,
                    ResourceOwnership.MODIFIED_BY_INSTALLER.value,
                )
        return False

    # ─── Checkpoints ─────────────────────────────────────────────────────

    def create_checkpoint(self, stage_name: str, data: dict) -> str:
        """Create a checkpoint before a risky operation."""
        checkpoint_file = os.path.join(self._checkpoint_dir, f"{stage_name}.json")
        checkpoint_data = {
            "stage": stage_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f, indent=2)
        logger.debug(f"Checkpoint created: {stage_name}")
        return checkpoint_file

    def load_checkpoint(self, stage_name: str) -> Optional[dict]:
        """Load a checkpoint for a stage."""
        checkpoint_file = os.path.join(self._checkpoint_dir, f"{stage_name}.json")
        if os.path.isfile(checkpoint_file):
            with open(checkpoint_file, "r") as f:
                return json.load(f)
        return None

    # ─── Backup ──────────────────────────────────────────────────────────

    def create_backup(self, stage_name: str, files: list[str]) -> str:
        """Backup files before modification."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_path = os.path.join(self._backup_dir, timestamp, stage_name)
        Path(backup_path).mkdir(parents=True, exist_ok=True)

        for filepath in files:
            if os.path.exists(filepath):
                dest = os.path.join(backup_path, os.path.basename(filepath))
                shutil.copy2(filepath, dest)
                logger.debug(f"Backed up: {filepath} -> {dest}")

        return backup_path

    # ─── Manifest ────────────────────────────────────────────────────────

    def update_manifest(self, key: str, value: Any) -> None:
        """Update the installation manifest."""
        self._manifest[key] = value
        tmp_path = self._manifest_file + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(self._manifest, f, indent=2)
        os.replace(tmp_path, self._manifest_file)

    def get_manifest(self) -> dict:
        return dict(self._manifest)

    # ─── Status summary ──────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Get a summary of all stage statuses."""
        summary = {}
        for name in INSTALLATION_STAGES:
            stage = self.get_stage(name)
            summary[name] = {
                "status": stage.status,
                "attempt": stage.attempt,
                "error": stage.error_message,
            }
        return summary

    @property
    def installation_id(self) -> str:
        return self._installation_id
