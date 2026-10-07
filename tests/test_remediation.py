import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.command import CommandRunner
from cape_auto.state import StateManager
from cape_auto.remediation import RemediationEngine, RiskLevel


class TestRemediation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cmd = CommandRunner(dry_run=True)
        self.state = StateManager(
            state_dir=os.path.join(self.temp_dir.name, "state"),
            backup_dir=os.path.join(self.temp_dir.name, "backups"),
        )
        self.engine = RemediationEngine(
            cmd=self.cmd,
            state=self.state,
            allow_medium=True,
            allow_high=False,
            allow_destructive=False,
            is_remote=False,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_risk_levels_and_auto_execute(self):
        self.assertTrue(self.engine.can_auto_execute(RiskLevel.LOW.value))
        self.assertTrue(self.engine.can_auto_execute(RiskLevel.MEDIUM.value))
        self.assertFalse(self.engine.can_auto_execute(RiskLevel.HIGH.value))
        self.assertFalse(self.engine.can_auto_execute(RiskLevel.DESTRUCTIVE.value))

    def test_remote_mode_safety(self):
        remote_engine = RemediationEngine(
            cmd=self.cmd,
            state=self.state,
            allow_medium=True,
            allow_high=True,  # requested high, but is_remote=True
            allow_destructive=False,
            is_remote=True,
        )
        self.assertFalse(remote_engine.can_auto_execute(RiskLevel.HIGH.value))

    def test_classify_errors(self):
        self.assertEqual(
            self.engine.classify_error("dpkg: error processing package", 1),
            "PACKAGE_ERROR",
        )
        self.assertEqual(
            self.engine.classify_error("Permission denied: /opt/CAPEv2", 1),
            "PERMISSION_ERROR",
        )
        self.assertEqual(
            self.engine.classify_error("error: could not connect to virsh daemon", 1),
            "LIBVIRT_ERROR",
        )
        self.assertEqual(
            self.engine.classify_error("ModuleNotFoundError: No module named 'cuckoo'", 1),
            "PYTHON_ERROR",
        )
        self.assertEqual(
            self.engine.classify_error("Failed to start mongod.service: Unit not found", 1),
            "SERVICE_ERROR",
        )
        self.assertEqual(
            self.engine.classify_error("Command not found", 127),
            "PACKAGE_ERROR",
        )

    def test_get_repair_for_error(self):
        repairs = self.engine.get_repair_for_error("PACKAGE_ERROR")
        self.assertGreater(len(repairs), 0)
        self.assertEqual(repairs[0].remediation_id, "repair_apt")
        self.assertEqual(repairs[0].risk_level, RiskLevel.LOW.value)


if __name__ == "__main__":
    unittest.main()
