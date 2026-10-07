"""
Custom exceptions for the CAPEv2 Automated Installer.

Structured exception hierarchy for precise error classification
and appropriate remediation routing.
"""


class CapeAutoError(Exception):
    """Base exception for all cape-auto errors."""
    pass


class PreflightError(CapeAutoError):
    """Environment does not meet minimum requirements."""
    pass


class CommandError(CapeAutoError):
    """A shell command failed."""
    def __init__(self, message: str, command: str = "", exit_code: int = -1,
                 stdout: str = "", stderr: str = "", category: str = "UNKNOWN_ERROR"):
        super().__init__(message)
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.category = category


class VerificationError(CapeAutoError):
    """A postcondition check failed after an operation."""
    pass


class RepairError(CapeAutoError):
    """A repair attempt failed."""
    pass


class ConfigurationError(CapeAutoError):
    """Configuration is invalid or missing required values."""
    pass


ConfigError = ConfigurationError


class RebootRequired(CapeAutoError):
    """A reboot is needed before the installation can continue."""
    pass


class ManualInterventionRequired(CapeAutoError):
    """A problem that cannot be automatically resolved."""
    def __init__(self, message: str, report_path: str = ""):
        super().__init__(message)
        self.report_path = report_path


class StageError(CapeAutoError):
    """An installation stage failed."""
    def __init__(self, message: str, stage: str = "", recoverable: bool = True):
        super().__init__(message)
        self.stage = stage
        self.recoverable = recoverable


class NetworkError(CapeAutoError):
    """Network-related failure."""
    pass


class PackageError(CapeAutoError):
    """Package management failure."""
    pass


class DatabaseError(CapeAutoError):
    """Database-related failure."""
    pass


class LibvirtError(CapeAutoError):
    """Libvirt/KVM-related failure."""
    pass


class VMError(CapeAutoError):
    """Virtual machine operation failure."""
    pass


class PythonEnvError(CapeAutoError):
    """Python environment failure."""
    pass


class TimeoutError(CapeAutoError):
    """Operation timed out."""
    pass
