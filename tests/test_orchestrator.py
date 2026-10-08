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

    def test_windows_eval_catalog(self):
        from cape_auto.orchestrator import WINDOWS_EVAL_CATALOG
        self.assertIn("win10_eval", WINDOWS_EVAL_CATALOG)
        self.assertIn("win11_eval", WINDOWS_EVAL_CATALOG)

        win10 = WINDOWS_EVAL_CATALOG["win10_eval"]
        self.assertEqual(win10["os_variant"], "win10")
        self.assertTrue(len(win10["urls"]) >= 2)
        self.assertIn("microsoft.com", win10["urls"][0])

        win11 = WINDOWS_EVAL_CATALOG["win11_eval"]
        self.assertEqual(win11["os_variant"], "win11")
        self.assertTrue(win11["needs_uefi"])
        self.assertTrue(len(win11["urls"]) >= 2)

    def test_tiny11_strictly_prohibited(self):
        from cape_auto.orchestrator import validate_iso_policy
        from cape_auto.exceptions import StageError

        # Tiny11 and stripped variants must be strictly rejected
        bad_paths = [
            "/iso/tiny11_b2.iso",
            "C:\\ISOs\\Tiny-11-23h2.iso",
            "/var/lib/images/tiny10-x64.iso",
            "https://archive.org/tiny11.iso",
            "/home/user/micro10.iso",
            "/home/user/ghostspectre.iso",
        ]
        for path in bad_paths:
            with self.assertRaises(StageError, msg=f"Should reject {path}") as ctx:
                validate_iso_policy(path)
            self.assertIn("Tiny11", str(ctx.exception))
            self.assertIn("PROHIBITED", str(ctx.exception))

        # Official evaluation ISOs must be allowed without error
        good_paths = [
            "/var/lib/libvirt/images/win10-enterprise-eval.iso",
            "/var/lib/libvirt/images/win11-enterprise-eval.iso",
            "https://software-static.download.prss.microsoft.com/dbazure/win10.iso",
            "",
        ]
        for path in good_paths:
            validate_iso_policy(path)

    def test_render_ascii_progress_bar(self):
        from cape_auto.orchestrator import render_ascii_progress_bar

        bar_0 = render_ascii_progress_bar(0, 24, width=20)
        self.assertIn("0%", bar_0)

        bar_half = render_ascii_progress_bar(12, 24, width=20)
        self.assertIn("50%", bar_half)
        self.assertIn("█", bar_half)
        self.assertIn("░", bar_half)

        bar_full = render_ascii_progress_bar(24, 24, width=20)
        self.assertIn("100%", bar_full)
        self.assertNotIn("░", bar_full)


if __name__ == "__main__":
    unittest.main()
