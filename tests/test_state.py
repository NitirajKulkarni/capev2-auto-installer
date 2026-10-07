import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.state import (
    StateManager, StageStatus, ResourceOwnership, HealthStatus,
    INSTALLATION_STAGES,
)


class TestState(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = os.path.join(self.temp_dir.name, "state")
        self.backup_dir = os.path.join(self.temp_dir.name, "backups")
        self.manager = StateManager(state_dir=self.state_dir, backup_dir=self.backup_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_stage_lifecycle(self):
        stage = "PREFLIGHT"
        self.manager.start_stage(stage)
        st = self.manager.get_stage(stage)
        self.assertEqual(st.status, StageStatus.RUNNING.value)

        self.manager.complete_stage(stage, verified=True)
        st = self.manager.get_stage(stage)
        self.assertEqual(st.status, StageStatus.SUCCESS.value)
        self.assertTrue(st.verification_passed)

    def test_stage_failure(self):
        stage = "BASE_PACKAGES"
        self.manager.start_stage(stage)
        self.manager.fail_stage(stage, error="Package broken")
        st = self.manager.get_stage(stage)
        self.assertEqual(st.status, StageStatus.FAILED.value)
        self.assertEqual(st.error_message, "Package broken")

        failed = self.manager.get_failed_stages()
        self.assertIn(stage, failed)

    def test_resume_stage(self):
        self.manager.complete_stage("PREFLIGHT")
        self.manager.complete_stage("BACKUP")
        self.manager.fail_stage("REPOSITORIES", error="network failure")
        resume = self.manager.get_resume_stage()
        self.assertEqual(resume, "REPOSITORIES")

    def test_checkpoint(self):
        self.manager.create_checkpoint("STAGE_1", {"test_key": 123})
        cp = self.manager.load_checkpoint("STAGE_1")
        self.assertIsNotNone(cp)
        self.assertEqual(cp["data"]["test_key"], 123)

    def test_resource_ownership(self):
        self.manager.register_resource("systemd_service", "cape", ResourceOwnership.CREATED_BY_INSTALLER)
        self.manager.register_resource("systemd_service", "nginx", ResourceOwnership.PRE_EXISTING)

        self.assertTrue(self.manager.is_owned_by_us("systemd_service", "cape"))
        self.assertFalse(self.manager.is_owned_by_us("systemd_service", "nginx"))
        self.assertFalse(self.manager.is_owned_by_us("systemd_service", "unknown_service"))

    def test_manifest_and_persistence(self):
        self.manager.update_manifest("os_version", "Ubuntu 24.04")

        # Load fresh instance from same directory
        new_manager = StateManager(state_dir=self.state_dir, backup_dir=self.backup_dir)
        manifest = new_manager.get_manifest()
        self.assertEqual(manifest.get("os_version"), "Ubuntu 24.04")

    def test_stage_from_index(self):
        idx = self.manager.get_stage_from("KVM")
        self.assertIsNotNone(idx)
        self.assertEqual(INSTALLATION_STAGES[idx], "KVM")


if __name__ == "__main__":
    unittest.main()
