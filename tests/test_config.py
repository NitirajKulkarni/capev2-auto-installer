import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from cape_auto.config import Config, _MinimalTOMLParser
from cape_auto.exceptions import ConfigError


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.toml")
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("""
[installation]
cape_root = "/opt/test/CAPEv2"
cape_user = "testcape"
auto_repair = true
max_repair_attempts = 5

[network]
mode = "nat"
gateway = "192.168.250.1"

[guest]
enabled = false
name = "test-vm"
disk_size_gb = 50
""")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_minimal_toml_parser(self):
        text = """
[test]
key1 = "value1"
key2 = true
key3 = 42
key4 = 3.14
"""
        parsed = _MinimalTOMLParser.loads(text)
        self.assertEqual(parsed["test"]["key1"], "value1")
        self.assertIs(parsed["test"]["key2"], True)
        self.assertEqual(parsed["test"]["key3"], 42)
        self.assertEqual(parsed["test"]["key4"], 3.14)

    def test_load_and_get(self):
        config = Config(self.config_path, self.temp_dir.name)
        self.assertEqual(config.get_str("installation.cape_root"), "/opt/test/CAPEv2")
        self.assertEqual(config.get_str("installation.cape_user"), "testcape")
        self.assertTrue(config.get_bool("installation.auto_repair"))
        self.assertEqual(config.get_int("installation.max_repair_attempts"), 5)
        self.assertFalse(config.get_bool("guest.enabled"))
        self.assertEqual(config.get_int("guest.disk_size_gb"), 50)

    def test_default_values(self):
        config = Config(self.config_path, self.temp_dir.name)
        self.assertEqual(config.get_str("nonexistent.key", "fallback"), "fallback")
        self.assertTrue(config.get_bool("nonexistent.bool", True))
        self.assertEqual(config.get_int("nonexistent.int", 123), 123)

    def test_set_value(self):
        config = Config(self.config_path, self.temp_dir.name)
        config.set("installation.cape_user", "updated_user")
        self.assertEqual(config.get_str("installation.cape_user"), "updated_user")

    def test_validation(self):
        config = Config(self.config_path, self.temp_dir.name)
        warnings = config.validate()
        self.assertIsInstance(warnings, list)

    def test_missing_config_file(self):
        missing_path = os.path.join(self.temp_dir.name, "missing.toml")
        with self.assertRaises(ConfigError):
            Config(missing_path, self.temp_dir.name)


if __name__ == "__main__":
    unittest.main()
