import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.config import Config
from cape_auto.reporting import ReportGenerator
from cape_auto.state import StateManager


class TestReporting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reports_dir = os.path.join(self.temp_dir.name, "reports")
        self.state_dir = os.path.join(self.temp_dir.name, "state")
        self.backup_dir = os.path.join(self.temp_dir.name, "backups")
        self.config_path = os.path.join(self.temp_dir.name, "config.toml")

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("[installation]\ncape_root = '/opt/CAPEv2'\n")

        self.state = StateManager(state_dir=self.state_dir, backup_dir=self.backup_dir)
        self.config = Config(self.config_path, self.temp_dir.name)
        self.reporter = ReportGenerator(
            reports_dir=self.reports_dir,
            state=self.state,
            config=self.config,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_final_report_success(self):
        self.state.complete_stage("PREFLIGHT")
        self.reporter.generate_final_report(overall_success=True)

        md_path = os.path.join(self.reports_dir, "final-report.md")
        json_path = os.path.join(self.reports_dir, "final-report.json")

        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(os.path.isfile(json_path))

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("CAPEv2 Installation Report", content)
            self.assertIn("PREFLIGHT", content)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("result", data)
            self.assertIn("manifest", data)
            self.assertIn("stages", data)

    def test_generate_manual_intervention_report(self):
        report_path = self.reporter.generate_manual_intervention_report(
            stage="KVM",
            problem="Hardware virtualization disabled in BIOS",
        )
        self.assertTrue(os.path.isfile(report_path))
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Manual Intervention Required", content)
            self.assertIn("Hardware virtualization disabled in BIOS", content)
            self.assertIn("sudo ./install.sh --resume", content)


if __name__ == "__main__":
    unittest.main()
