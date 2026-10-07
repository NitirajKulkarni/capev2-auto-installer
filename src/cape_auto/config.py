"""
Configuration management for CAPEv2 Automated Installer.

Loads config.toml, merges environment variables, provides typed access,
and validates configuration completeness.
"""
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Python 3.11+ has tomllib; for 3.10 we provide a fallback
if sys.version_info >= (3, 11):
    import tomllib
else:
    # Minimal TOML parser for 3.10 compatibility (stdlib only)
    try:
        import tomllib  # type: ignore
    except ImportError:
        import tomli as tomllib  # type: ignore  # noqa: F811
        # If tomli is also unavailable, we implement a basic parser below


class _MinimalTOMLParser:
    """
    Extremely minimal TOML parser for bootstrapping on Python 3.10
    without pip packages. Supports basic key=value, [sections], strings,
    booleans, integers, and floats. Does NOT support arrays-of-tables,
    inline tables, multiline strings, etc.
    """

    @staticmethod
    def loads(text: str) -> dict:
        result: dict = {}
        current_section: Optional[list[str]] = None

        for line_num, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Section header
            if line.startswith("["):
                header = line.strip("[]").strip()
                current_section = header.split(".")
                # Ensure nested dict exists
                d = result
                for key in current_section:
                    if key not in d:
                        d[key] = {}
                    d = d[key]
                continue

            # Key = value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Remove inline comments
                if "#" in value:
                    # But not inside strings
                    in_str = False
                    for i, ch in enumerate(value):
                        if ch == '"' and (i == 0 or value[i - 1] != "\\"):
                            in_str = not in_str
                        elif ch == "#" and not in_str:
                            value = value[:i].strip()
                            break

                # Parse value
                parsed = _MinimalTOMLParser._parse_value(value)

                # Place in correct section
                d = result
                if current_section:
                    for sec_key in current_section:
                        d = d[sec_key]
                d[key] = parsed

        return result

    @staticmethod
    def _parse_value(value: str) -> Any:
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


class Config:
    """
    Configuration container with dotted-key access.

    Loads from config.toml, environment overrides, and provides
    typed getters with defaults.
    """

    def __init__(self, config_path: str, project_dir: str):
        self._project_dir = project_dir
        self._data: dict = {}
        self._config_path = config_path

        # Load config file
        if config_path:
            if not os.path.isfile(config_path):
                from cape_auto.exceptions import ConfigurationError
                raise ConfigurationError(f"Config file not found: {config_path}")
            self._load_toml(config_path)

        # Apply environment overrides
        self._apply_env_overrides()

    def _load_toml(self, path: str) -> None:
        """Load TOML configuration file."""
        content = Path(path).read_text(encoding="utf-8")
        try:
            if sys.version_info >= (3, 11):
                self._data = tomllib.loads(content)
            else:
                try:
                    self._data = tomllib.loads(content)
                except Exception:
                    self._data = _MinimalTOMLParser.loads(content)
        except Exception:
            self._data = _MinimalTOMLParser.loads(content)

    def _apply_env_overrides(self) -> None:
        """Override config from environment variables."""
        env_map = {
            "CAPE_ROOT": "installation.cape_root",
            "CAPE_USER": "installation.cape_user",
            "CAPE_REPO": "installation.cape_repo",
            "CAPE_REF": "installation.cape_ref",
            "CAPE_NON_INTERACTIVE": "installation.non_interactive",
            "CAPE_PYTHON_MANAGER": "installation.python_manager",
            "HTTP_PROXY": "proxy.http_proxy",
            "HTTPS_PROXY": "proxy.https_proxy",
            "NO_PROXY": "proxy.no_proxy",
            "ALL_PROXY": "proxy.http_proxy",
        }
        for env_var, config_key in env_map.items():
            val = os.environ.get(env_var)
            if val is not None:
                self.set(config_key, val)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Get a config value using dotted notation: 'section.key'"""
        keys = dotted_key.split(".")
        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, dotted_key: str, value: Any) -> None:
        """Set a config value using dotted notation."""
        keys = dotted_key.split(".")
        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        # Type coerce strings to bool
        if isinstance(value, str) and value.lower() in ("true", "false"):
            value = value.lower() == "true"
        d[keys[-1]] = value

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "yes", "1")
        return bool(val)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get(key, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        val = self.get(key, default)
        return str(val) if val is not None else default

    @property
    def project_dir(self) -> str:
        return self._project_dir

    @property
    def config_path(self) -> str:
        return self._config_path

    def as_dict(self) -> dict:
        """Return full configuration as dict (for serialization/reporting)."""
        import copy
        return copy.deepcopy(self._data)

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of warnings/issues.
        Does not raise - collects all problems.
        """
        issues: list[str] = []

        cape_root = self.get_str("installation.cape_root")
        if not cape_root:
            issues.append("installation.cape_root is empty")

        cape_user = self.get_str("installation.cape_user")
        if not cape_user:
            issues.append("installation.cape_user is empty")

        # Guest ISO check
        if self.get_bool("guest.enabled"):
            iso = self.get_str("guest.iso_path")
            if not iso:
                issues.append("guest.iso_path is empty - Windows guest provisioning will be skipped")

        # Network validation
        subnet = self.get_str("network.subnet")
        if not subnet:
            issues.append("network.subnet is empty")

        return issues
