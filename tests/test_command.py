import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.command import CommandRunner, CommandResult
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


if __name__ == "__main__":
    unittest.main()
