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
import re
import subprocess
import time
import threading
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


class LiveProgressTracker:
    """Tracks live progress for long-running commands and renders visual ASCII progress bars."""

    def __init__(self, command_str: str):
        self.cmd = command_str.lower()
        self.is_python_pkg = any(k in self.cmd for k in ["uv", "pip", "poetry"])
        self.is_disk_op = any(k in self.cmd for k in ["qemu-img", "virt-install", "dd"])
        self.is_git = "git" in self.cmd
        self.is_apt = any(k in self.cmd for k in ["apt-get", "apt ", "dpkg"])
        self.total_items: Optional[int] = None
        self.completed_items: int = 0
        self.pct: Optional[float] = None

        if self.is_python_pkg:
            self.current_activity = "Resolving & downloading dependencies..."
        elif self.is_disk_op:
            self.current_activity = "Processing disk image / VM storage..."
        elif self.is_git:
            self.current_activity = "Cloning repository..."
        elif self.is_apt:
            self.current_activity = "Installing system packages..."
        else:
            self.current_activity = "Processing..."

    def update_from_line(self, raw_line: str) -> None:
        line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_line).strip()
        if not line:
            return

        # uv / poetry dependency resolution: "Resolved 142 packages in 35ms"
        m_res = re.search(r"Resolved\s+(\d+)\s+packages", line, re.I)
        if m_res:
            self.total_items = int(m_res.group(1))
            self.current_activity = f"Resolved {self.total_items} packages"
            return

        # "Installed 45 packages"
        m_inst_count = re.search(r"Installed\s+(\d+)\s+packages", line, re.I)
        if m_inst_count:
            self.completed_items = int(m_inst_count.group(1))
            if self.total_items and self.total_items > 0:
                self.pct = (self.completed_items / self.total_items) * 100.0
            return

        # "Installed foo==1.0"
        m_inst_single = re.search(r"Installed\s+([a-zA-Z0-9_\-\.]+)", line, re.I)
        if m_inst_single:
            self.completed_items += 1
            pkg = m_inst_single.group(1)
            self.current_activity = f"Installed {pkg}"
            if self.total_items and self.total_items > 0:
                self.pct = (self.completed_items / self.total_items) * 100.0
            return

        # "Downloading yara-python" / "Building yara-python" / "Prepared yara-python"
        m_dl = re.search(r"(Downloading|Building|Prepared|Auditing)\s+([a-zA-Z0-9_\-\.]+)", line, re.I)
        if m_dl:
            act, pkg = m_dl.group(1), m_dl.group(2)
            self.current_activity = f"{act} {pkg}"
            return

        # git clone progress: "Receiving objects:  45% (1234/2742)"
        m_git = re.search(r"Receiving objects:\s+(\d+)%", line, re.I)
        if m_git:
            self.pct = float(m_git.group(1))
            self.current_activity = "Cloning git objects"
            return

        # qemu-img convert progress: "(45.20/100%)"
        m_qemu = re.search(r"\((\d+(?:\.\d+)?)%\)", line)
        if m_qemu:
            self.pct = float(m_qemu.group(1))
            self.current_activity = "Converting disk image"
            return

        m_pct_generic = re.search(r"\b(\d{1,3})%\b", line)
        if m_pct_generic:
            val = float(m_pct_generic.group(1))
            if 0 <= val <= 100:
                self.pct = val

    def render_bar(self, elapsed_s: int, width: int = 18) -> str:
        if self.pct is not None:
            pct_val = max(0.0, min(100.0, self.pct))
            filled = int(width * (pct_val / 100.0))
            bar = "#" * filled + "-" * (width - filled)
            if self.total_items and self.total_items > 0:
                stats = f" {self.completed_items}/{self.total_items} pkgs ({int(pct_val)}%)"
            else:
                stats = f" {int(pct_val)}%"
            return f"[{bar}]{stats} | {self.current_activity} | {elapsed_s}s elapsed"
        else:
            pulse = (elapsed_s // 2) % width
            bar_chars = ["-"] * width
            for i in range(4):
                bar_chars[(pulse + i) % width] = "#"
            bar = "".join(bar_chars)
            return f"[{bar}] {self.current_activity} | {elapsed_s}s elapsed"


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
                    stderr=subprocess.STDOUT,  # Merge stderr (where uv, pip, git stream progress) into stdout
                    text=True,
                    bufsize=1,
                )
                tracker = LiveProgressTracker(log_cmd)
                stdout_lines = []
                done_event = threading.Event()

                def _heartbeat():
                    while not done_event.wait(5.0):
                        elapsed_s = int(time.monotonic() - start_time)
                        if timeout and (time.monotonic() - start_time) > timeout:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            break
                        logger.info(f"  │ ⏳ [PROGRESS] {tracker.render_bar(elapsed_s)}")

                hb_thread = threading.Thread(target=_heartbeat, daemon=True)
                hb_thread.start()

                try:
                    while True:
                        if timeout and (time.monotonic() - start_time) > timeout:
                            timed_out = True
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            break
                        line = proc.stdout.readline()
                        if not line and proc.poll() is not None:
                            break
                        if line:
                            stdout_lines.append(line)
                            line_stripped = line.rstrip()
                            if line_stripped:
                                tracker.update_from_line(line_stripped)
                                if not sensitive:
                                    clean_line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line_stripped)
                                    logger.info(f"  │ {clean_line}")
                finally:
                    done_event.set()

                stdout = "".join(stdout_lines)
                exit_code = -1 if timed_out else proc.returncode
                if timed_out:
                    stderr = f"Command timed out after {timeout}s: {stdout}"
                    logger.error(f"  TIMEOUT after {timeout}s: {log_cmd}")
                else:
                    stderr = stdout if exit_code != 0 else ""
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
