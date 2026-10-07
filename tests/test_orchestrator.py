import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.config import Config
from cape_auto.orchestrator import Orchestrator
from cape_auto.state import INSTALLATION_STAGES


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.toml")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("""
[installation]
cape_root = "/opt/CAPEv2"
cape_user = "cape"
auto_repair = true
max_repair_attempts = 2

[network]
mode = "isolated"
gateway = "192.168.250.1"

[guest]
enabled = false
""")
        self.config = Config(self.config_path, self.temp_dir.name)
        self.orchestrator = Orchestrator(config=self.config, project_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_self_test(self):
        exit_code = self.orchestrator.self_test()
        self.assertEqual(exit_code, 0)

    def test_dry_run(self):
        exit_code = self.orchestrator.dry_run()
        self.assertEqual(exit_code, 0)

    def test_status(self):
        exit_code = self.orchestrator.status(drift=False)
        self.assertEqual(exit_code, 0)

    def test_stage_descriptions(self):
        for stage in INSTALLATION_STAGES:
            desc = self.orchestrator._get_stage_description(stage)
            self.assertIsInstance(desc, str)
            self.assertGreater(len(desc), 0)

    def test_is_blocking_failure(self):
        # Critical stages must be blocking
        self.assertTrue(self.orchestrator._is_blocking_failure("PREFLIGHT"))
        self.assertTrue(self.orchestrator._is_blocking_failure("KVM"))
        self.assertTrue(self.orchestrator._is_blocking_failure("LIBVIRT"))
        # Non-critical stages should not block whole installation
        self.assertFalse(self.orchestrator._is_blocking_failure("BACKUP"))
        self.assertFalse(self.orchestrator._is_blocking_failure("END_TO_END_TEST"))


if __name__ == "__main__":
    unittest.main()
