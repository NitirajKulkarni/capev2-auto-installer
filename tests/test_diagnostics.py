import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.command import CommandRunner
from cape_auto.diagnostics import DiagnosticsEngine, DiagnosticResult
from cape_auto.state import HealthStatus


class TestDiagnostics(unittest.TestCase):
    def setUp(self):
        self.cmd = CommandRunner(dry_run=True)
        self.diag = DiagnosticsEngine(cmd=self.cmd, cape_root="/opt/CAPEv2")

    def test_diagnostic_result_to_dict(self):
        res = DiagnosticResult(
            component="test_comp",
            status=HealthStatus.PASS.value,
            severity="low",
            symptoms=["symptom1"],
            probable_causes=["cause1"],
            recommended_repairs=["repair1"],
        )
        d = res.to_dict()
        self.assertEqual(d["component"], "test_comp")
        self.assertEqual(d["status"], "PASS")
        self.assertEqual(d["symptoms"], ["symptom1"])

    def test_generate_report(self):
        results = [
            DiagnosticResult(component="os", status=HealthStatus.PASS.value),
            DiagnosticResult(
                component="kvm",
                status=HealthStatus.FAIL.value,
                severity="critical",
                symptoms=["/dev/kvm missing"],
                probable_causes=["Virtualization disabled in BIOS"],
                recommended_repairs=["Enable VT-x/AMD-V"],
            ),
            DiagnosticResult(component="network", status=HealthStatus.WARN.value),
        ]
        report = self.diag.generate_report(results)
        self.assertIn("CAPEv2 Diagnostic Report", report)
        self.assertIn("os", report)
        self.assertIn("[PASS]", report)
        self.assertIn("kvm", report)
        self.assertIn("[FAIL]", report)
        self.assertIn("ISSUES DETECTED", report)

    def test_diagnose_all_dry_run(self):
        # Even with mock/dry-run, diagnose_all should execute all probes without unhandled crash
        results = self.diag.diagnose_all()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 5)
        components = [r.component for r in results]
        self.assertIn("os", components)
        self.assertIn("cpu", components)
        self.assertIn("kvm", components)
        self.assertIn("libvirt", components)


if __name__ == "__main__":
    unittest.main()
