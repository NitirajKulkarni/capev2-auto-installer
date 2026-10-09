"""
Command execution engine for CAPEv2 Automated Installer.

Provides safe, logged, timeout-aware command execution with:
- Exit code, stdout, stderr capture
- Timeout enforcement
- Secret redaction
- Retry support
- User context switching (sudo -u)
- Pipeline support with PIPESTATUS
"""
import os
import subprocess
import time
import shlex
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from cape_auto.logging_setup import get_logger

logger = get_logger("command")


@dataclass
class CommandResult:
    """Result of a command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False
    success: bool = False
    cwd: str = ""
    env_extra: dict = field(default_factory=dict)

    def __post_init__(self):
        self.success = self.exit_code == 0 and not self.timed_out


class CommandRunner:
    """
    Safe command execution with logging, timeouts, and retries.

    Never uses uncontrolled shell=True by default.
    Logs all executions with timestamps and results.
    Redacts sensitive content in logs.
    """

    # Words that indicate a command argument is sensitive
    SENSITIVE_ARGS = {"password", "passwd", "secret", "token", "key", "auth"}

    def __init__(self, dry_run: bool = False):
        self._dry_run = dry_run
        self._history: list[CommandResult] = []

    @property
    def history(self) -> list[CommandResult]:
        return self._history

    def _redact_command(self, cmd: str) -> str:
        """Redact sensitive values from command strings for logging."""
        parts = cmd.split()
        redacted = []
        skip_next = False
        for i, part in enumerate(parts):
            if skip_next:
                redacted.append("[REDACTED]")
                skip_next = False
                continue
            lower = part.lower().rstrip("=")
            if any(s in lower for s in self.SENSITIVE_ARGS):
                if "=" in part:
                    key, _, _ = part.partition("=")
                    redacted.append(f"{key}=[REDACTED]")
                else:
                    redacted.append(part)
                    skip_next = True
            else:
                redacted.append(part)
        return " ".join(redacted)

    def run(
        self,
        command: list[str] | str,
        *,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        timeout: int = 300,
        check: bool = False,
        acceptable_codes: Optional[list[int]] = None,
        sensitive: bool = False,
        shell: bool = False,
        input_data: Optional[str] = None,
        live_output: bool = False,
        quiet: bool = False,
    ) -> CommandResult:
        """
        Execute a command with full instrumentation.

        Args:
            command: Command as list of args or string (if shell=True)
            cwd: Working directory
            env: Additional environment variables (merged with current)
            timeout: Timeout in seconds
            check: Raise CommandError on failure
            acceptable_codes: List of acceptable exit codes (default: [0])
            sensitive: If True, redact entire command from logs
            shell: Use shell execution (only when necessary, e.g. pipes)
            input_data: Data to send to stdin
            live_output: Stream stdout lines in real time to logger
            quiet: If True, log EXEC and EXIT at DEBUG level instead of INFO
        """
        from cape_auto.exceptions import CommandError

        if acceptable_codes is None:
            acceptable_codes = [0]

        # Build command string for logging
        if isinstance(command, list):
            cmd_str = " ".join(shlex.quote(str(c)) for c in command)
        else:
            cmd_str = command

        log_cmd = "[SENSITIVE COMMAND]" if sensitive else self._redact_command(cmd_str)
        if quiet:
            logger.debug(f"EXEC: {log_cmd}")
        else:
            logger.info(f"EXEC: {log_cmd}")
        if cwd:
            logger.debug(f"  CWD: {cwd}")

        if self._dry_run:
            logger.info(f"  [DRY-RUN] Would execute: {log_cmd}")
            result = CommandResult(
                command=cmd_str, exit_code=0, stdout="[dry-run]",
                stderr="", duration=0.0, cwd=cwd or ""
            )
            self._history.append(result)
            return result

        # Build environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        # Ensure non-interactive apt
        run_env["DEBIAN_FRONTEND"] = "noninteractive"

        start_time = time.monotonic()
        timed_out = False

        try:
            if live_output and not input_data:
                proc = subprocess.Popen(
                    command if not shell else cmd_str,
                    shell=shell,
                    cwd=cwd,
                    env=run_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                stdout_lines = []
                while True:
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break
                    if line:
                        stdout_lines.append(line)
                        line_stripped = line.rstrip()
                        if line_stripped and not sensitive:
                            logger.info(f"  │ {line_stripped}")
                stderr = proc.stderr.read() or ""
                stdout = "".join(stdout_lines)
                exit_code = proc.returncode
            else:
                proc = subprocess.run(
                    command if not shell else cmd_str,
                    shell=shell,
                    cwd=cwd,
                    env=run_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    input=input_data,
                )
                exit_code = proc.returncode
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""

        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            stdout = ""
            stderr = f"Command timed out after {timeout}s"
            logger.error(f"  TIMEOUT after {timeout}s: {log_cmd}")

        except FileNotFoundError as e:
            exit_code = 127
            stdout = ""
            stderr = str(e)
            logger.error(f"  NOT FOUND: {e}")

        except PermissionError as e:
            exit_code = 126
            stdout = ""
            stderr = str(e)
            logger.error(f"  PERMISSION DENIED: {e}")

        except Exception as e:
            exit_code = -1
            stdout = ""
            stderr = str(e)
            logger.error(f"  EXCEPTION: {e}")

        duration = time.monotonic() - start_time

        result = CommandResult(
            command=cmd_str,
            exit_code=exit_code,
            stdout=stdout.strip(),
            stderr=stderr.strip(),
            duration=round(duration, 3),
            timed_out=timed_out,
            cwd=cwd or "",
        )
        self._history.append(result)

        # Log result
        if quiet:
            logger.debug(f"  EXIT: {exit_code} ({duration:.1f}s)")
        else:
            logger.info(f"  EXIT: {exit_code} ({duration:.1f}s)")
        if exit_code != 0 and not sensitive:
            if stderr:
                # Limit stderr logging
                stderr_lines = stderr.splitlines()
                if len(stderr_lines) > 20:
                    logger.debug(f"  STDERR (first 20 lines):\n" +
                                "\n".join(stderr_lines[:20]) + "\n  ...")
                else:
                    logger.debug(f"  STDERR:\n{stderr}")

        if check and exit_code not in acceptable_codes:
            raise CommandError(
                message=f"Command failed: {log_cmd}",
                command=cmd_str,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
            )

        return result

    def run_checked(
        self,
        command: list[str] | str,
        **kwargs,
    ) -> CommandResult:
        """Run a command and raise on failure."""
        kwargs["check"] = True
        return self.run(command, **kwargs)

    def run_capture(
        self,
        command: list[str] | str,
        **kwargs,
    ) -> str:
        """Run a command and return stdout. Empty string on failure."""
        result = self.run(command, **kwargs)
        return result.stdout if result.success else ""

    def run_as_user(
        self,
        command: list[str] | str,
        user: str,
        env: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> CommandResult:
        """Run a command as a specific user via sudo -u, preserving environment variables."""
        env_dict = kwargs.pop("env", None) or env
        env_args = [f"{k}={v}" for k, v in env_dict.items()] if env_dict else []
        if isinstance(command, list):
            if env_args:
                full_cmd = ["sudo", "-u", user, "--", "env"] + env_args + command
            else:
                full_cmd = ["sudo", "-u", user, "--"] + command
        else:
            env_prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env_dict.items()) + " " if env_dict else ""
            full_cmd = f"sudo -u {shlex.quote(user)} -- {env_prefix}{command}"
            kwargs["shell"] = True
        return self.run(full_cmd, **kwargs)

    def run_sudo(
        self,
        command: list[str] | str,
        **kwargs,
    ) -> CommandResult:
        """Run a command with sudo (for cases where we need explicit sudo)."""
        if isinstance(command, list):
            full_cmd = ["sudo"] + command
        else:
            full_cmd = f"sudo {command}"
            kwargs["shell"] = True
        return self.run(full_cmd, **kwargs)

    def run_with_retry(
        self,
        command: list[str] | str,
        *,
        max_attempts: int = 3,
        delay: float = 5.0,
        backoff: float = 2.0,
        **kwargs,
    ) -> CommandResult:
        """Run a command with retry logic and exponential backoff."""
        last_result = None
        current_delay = delay

        for attempt in range(1, max_attempts + 1):
            logger.info(f"  Attempt {attempt}/{max_attempts}")
            result = self.run(command, **kwargs)
            if result.success:
                return result
            last_result = result
            if attempt < max_attempts:
                logger.warning(f"  Retrying in {current_delay:.0f}s...")
                time.sleep(current_delay)
                current_delay *= backoff

        return last_result  # type: ignore

    def test_command_exists(self, cmd: str) -> bool:
        """Test whether a command exists on the system."""
        result = self.run(["which", cmd], timeout=10)
        return result.success

    def get_command_path(self, cmd: str) -> Optional[str]:
        """Get the full path of a command."""
        result = self.run(["which", cmd], timeout=10)
        return result.stdout.strip() if result.success else None
