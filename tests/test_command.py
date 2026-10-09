import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.command import CommandRunner, CommandResult, LiveProgressTracker
from cape_auto.exceptions import CommandError


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.runner = CommandRunner(dry_run=False)

    def test_run_python_success(self):
        res = self.runner.run([sys.executable, "-c", "print('hello_cape')"])
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout, "hello_cape")
        self.assertFalse(res.timed_out)

    def test_run_failure_exit_code(self):
        res = self.runner.run([sys.executable, "-c", "import sys; sys.exit(42)"])
        self.assertFalse(res.success)
        self.assertEqual(res.exit_code, 42)

    def test_run_checked_raises(self):
        with self.assertRaises(CommandError) as ctx:
            self.runner.run_checked([sys.executable, "-c", "import sys; sys.exit(7)"])
        self.assertEqual(ctx.exception.exit_code, 7)

    def test_run_capture(self):
        out = self.runner.run_capture([sys.executable, "-c", "print('captured_output')"])
        self.assertEqual(out, "captured_output")

        # Capture on failure should return empty string
        fail_out = self.runner.run_capture([sys.executable, "-c", "import sys; sys.exit(1)"])
        self.assertEqual(fail_out, "")

    def test_dry_run_mode(self):
        dry_runner = CommandRunner(dry_run=True)
        res = dry_runner.run([sys.executable, "-c", "print('should_not_run')"])
        self.assertTrue(res.success)
        self.assertEqual(res.stdout, "[dry-run]")
        self.assertEqual(len(dry_runner.history), 1)

    def test_redact_command(self):
        redacted = self.runner._redact_command("install --password supersecret123 --name admin")
        self.assertNotIn("supersecret123", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_timeout(self):
        # Run a sleep command that exceeds 1 second timeout
        res = self.runner.run(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=1,
        )
        self.assertTrue(res.timed_out)
        self.assertFalse(res.success)
        self.assertIn("timed out", res.stderr.lower())

    def test_live_output_execution(self):
        script = "import sys\nprint('line1')\nprint('line2')\n"
        res = self.runner.run(
            [sys.executable, "-c", script],
            live_output=True,
        )
        self.assertTrue(res.success)
        self.assertIn("line1", res.stdout)
        self.assertIn("line2", res.stdout)

    def test_live_output_timeout(self):
        res = self.runner.run(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            live_output=True,
            timeout=1,
        )
        self.assertTrue(res.timed_out)
        self.assertFalse(res.success)
        self.assertIn("timed out", res.stderr.lower())

    def test_live_progress_tracker(self):
        tracker = LiveProgressTracker("uv sync -v --python 3.12")
        self.assertIsNone(tracker.pct)
        self.assertIn("dependencies", tracker.current_activity.lower())

        # Test wave progress bar
        bar_wave = tracker.render_bar(5)
        self.assertIn("elapsed", bar_wave)

        # Update resolution
        tracker.update_from_line("Resolved 100 packages in 12ms")
        self.assertEqual(tracker.total_items, 100)

        # Update packages installed
        tracker.update_from_line("Installed django==4.2")
        self.assertEqual(tracker.completed_items, 1)
        self.assertEqual(tracker.pct, 1.0)
        bar_pct = tracker.render_bar(10)
        self.assertIn("1/100 pkgs", bar_pct)
        self.assertIn("1%", bar_pct)


if __name__ == "__main__":
    unittest.main()
