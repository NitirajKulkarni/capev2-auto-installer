import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.cli import build_parser


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_default_args(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.resume)
        self.assertFalse(args.repair)
        self.assertFalse(args.diagnose)
        self.assertFalse(args.status)
        self.assertFalse(args.dry_run)
        self.assertFalse(args.preflight)
        self.assertFalse(args.self_test)
        self.assertFalse(args.uninstall)
        self.assertFalse(args.clean_install)

    def test_mutually_exclusive_modes(self):
        # Specifying mutually exclusive modes should raise SystemExit (parse error)
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--resume", "--repair"])

        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--status", "--diagnose"])

        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--clean-install", "--resume"])

    def test_individual_modes(self):
        args = self.parser.parse_args(["--resume"])
        self.assertTrue(args.resume)

        args = self.parser.parse_args(["--clean-install"])
        self.assertTrue(args.clean_install)

        args = self.parser.parse_args(["--clean"])
        self.assertTrue(args.clean_install)

        args = self.parser.parse_args(["--diagnose", "--watch"])
        self.assertTrue(args.diagnose)
        self.assertTrue(args.watch)

        args = self.parser.parse_args(["--status", "--drift"])
        self.assertTrue(args.status)
        self.assertTrue(args.drift)

        args = self.parser.parse_args(["--from-stage", "KVM"])
        self.assertEqual(args.from_stage, "KVM")

        args = self.parser.parse_args(["--non-interactive"])
        self.assertTrue(args.non_interactive)

    def test_uninstall_flags(self):
        args = self.parser.parse_args([
            "--uninstall", "--keep-cape-user", "--keep-data", "--keep-vm", "--full-reset"
        ])
        self.assertTrue(args.uninstall)
        self.assertTrue(args.keep_cape_user)
        self.assertTrue(args.keep_data)
        self.assertTrue(args.keep_vm)
        self.assertTrue(args.full_reset)


    def test_windows_edition_args(self):
        args1 = self.parser.parse_args(["--windows-edition", "win11_Eval"])
        self.assertEqual(args1.windows_edition, "win11_eval")

        args2 = self.parser.parse_args(["--windows-edition", "Win10_EVAL"])
        self.assertEqual(args2.windows_edition, "win10_eval")

        args3 = self.parser.parse_args(["--windows-edition", "win11"])
        self.assertEqual(args3.windows_edition, "win11_eval")

        args4 = self.parser.parse_args(["--windows-edition", "win10"])
        self.assertEqual(args4.windows_edition, "win10_eval")

        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--windows-edition", "invalid_os"])


if __name__ == "__main__":
    unittest.main()

