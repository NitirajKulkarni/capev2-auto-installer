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
        self.assertTrue(self.orchestrator._is_blocking_failure("VM_CREATE"))
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

    def test_autounattend_xml_schema_and_commands(self):
        import xml.etree.ElementTree as ET
        from pathlib import Path
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "windows", "autounattend.xml")
        self.assertTrue(os.path.isfile(template_path))

        tree = ET.parse(template_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "{urn:schemas-microsoft-com:unattend}unattend")

        content = Path(template_path).read_text(encoding="utf-8")
        self.assertIn("xmlns:wcm", content)
        self.assertIn("BypassTPMCheck", content)
        self.assertIn("BypassSecureBootCheck", content)
        self.assertIn("setup-agent.ps1", content)
        self.assertIn("FirstLogonCommands", content)
        self.assertIn("<Username>cape</Username>", content)

    def test_setup_agent_ps1_configuration(self):
        from pathlib import Path
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "windows", "setup-agent.ps1")
        self.assertTrue(os.path.isfile(template_path))
        content = Path(template_path).read_text(encoding="utf-8")

        self.assertIn("192.168.250.100", content)
        self.assertIn("Set-MpPreference", content)
        self.assertIn("EnableLUA", content)
        self.assertIn("wuauserv", content)
        self.assertIn("Set-NetFirewallProfile", content)
        self.assertIn("http://+:8000/", content)
        self.assertIn("start-cape-agent.bat", content)

    def test_generate_unattended_iso_call(self):
        from unittest.mock import MagicMock
        mock_cmd = MagicMock()
        mock_cmd.run.return_value.success = True
        self.orchestrator._cmd = mock_cmd

        tpl_dir = os.path.join(self.temp_dir.name, "templates", "windows")
        os.makedirs(tpl_dir, exist_ok=True)
        with open(os.path.join(tpl_dir, "autounattend.xml"), "w") as f:
            f.write("<unattend/>")
        with open(os.path.join(tpl_dir, "setup-agent.ps1"), "w") as f:
            f.write("Write-Output 'Agent'")

        iso_path = self.orchestrator._generate_unattended_iso("test-vm")
        self.assertIn("test-vm-unattend.iso", iso_path)

        calls = [c[0][0] for c in mock_cmd.run.call_args_list]
        found_oemdrv = any("OEMDRV" in cmd for cmd in calls)
        self.assertTrue(found_oemdrv)

    def test_clean_install_dry_run(self):
        self.orchestrator._dry_run_mode = True
        exit_code = self.orchestrator.clean_install()
        self.assertEqual(exit_code, 0)

    def test_clean_install_teardown(self):
        from unittest.mock import MagicMock
        mock_cmd = MagicMock()
        mock_cmd.run.return_value.success = True
        mock_cmd.run_capture.return_value = "cape-win"
        self.orchestrator._cmd = mock_cmd
        self.orchestrator.install = MagicMock(return_value=0)

        # Create dummy state and files
        state_file = os.path.join(self.temp_dir.name, "state", "test.json")
        with open(state_file, "w") as f:
            f.write("{}")

        exit_code = self.orchestrator.clean_install()
        self.assertEqual(exit_code, 0)
        self.orchestrator.install.assert_called_once()

        # Verify virsh destroy/undefine calls
        calls = [c[0][0] for c in mock_cmd.run.call_args_list]
        found_destroy = any("destroy" in cmd for cmd in calls)
        found_undefine = any("undefine" in cmd for cmd in calls)
        self.assertTrue(found_destroy)
        self.assertTrue(found_undefine)


    def test_download_iso_http416_recovery(self):
        from unittest.mock import patch, MagicMock
        import urllib.error

        dest_iso = os.path.join(self.temp_dir.name, "win11-eval.iso")
        part_iso = dest_iso + ".part"

        # Create a tiny invalid leftover part file
        with open(part_iso, "wb") as f:
            f.write(b"x" * 50)

        # First call: raises HTTPError 416 (Range Not Satisfiable)
        err_416 = urllib.error.HTTPError("http://example.com", 416, "Range Not Satisfiable", {}, None)

        # Second call: returns valid response context manager
        resp_mock = MagicMock()
        resp_mock.__enter__.return_value = resp_mock
        resp_mock.getcode.return_value = 200
        resp_mock.headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": "5368709120",
        }
        resp_mock.read.side_effect = [b"MOCK_ISO_DATA", b""]

        real_getsize = os.path.getsize

        def fake_getsize(path):
            if path == part_iso:
                return 5368709120
            return real_getsize(path)

        with patch("urllib.request.urlopen", side_effect=[err_416, resp_mock]), \
             patch("os.path.getsize", side_effect=fake_getsize):
            result = self.orchestrator._download_windows_eval_iso("win11_eval", dest_iso)

        self.assertEqual(result, dest_iso)
        self.assertTrue(os.path.isfile(dest_iso))
        self.assertFalse(os.path.isfile(part_iso))


if __name__ == "__main__":
    unittest.main()


