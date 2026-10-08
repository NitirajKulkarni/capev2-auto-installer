#!/usr/bin/env python3
"""
CAPEv2 Automated Installer - Command Line Interface

This is the main entry point called by install.sh after Python is bootstrapped.
All arguments are parsed here and delegated to the orchestrator.
"""
import sys
import os
import argparse

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cape_auto.orchestrator import Orchestrator
from cape_auto.config import Config
from cape_auto.logging_setup import setup_logging, get_logger
from cape_auto.exceptions import (
    CapeAutoError, RebootRequired, ManualInterventionRequired,
    PreflightError
)


def normalize_windows_edition(val: str) -> str:
    """Normalize Windows edition string (case-insensitive with common aliases)."""
    v = val.strip().lower()
    if v in ("win10", "win10_eval", "windows10", "windows-10", "windows 10"):
        return "win10_eval"
    if v in ("win11", "win11_eval", "windows11", "windows-11", "windows 11"):
        return "win11_eval"
    raise argparse.ArgumentTypeError(
        f"Invalid Windows edition '{val}'. Choose from win10_eval, win11_eval (or win10, win11)."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cape-auto-installer",
        description="CAPEv2 Automated Installation, Diagnosis, and Recovery Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo ./install.sh                    Full installation
  sudo ./install.sh --resume           Resume after interruption
  sudo ./install.sh --diagnose         Run diagnostics only
  sudo ./install.sh --repair           Repair broken installation
  sudo ./install.sh --status           Show current status
  sudo ./install.sh --dry-run          Preview actions
  sudo ./install.sh --preflight        Run preflight only
  sudo ./install.sh --from-stage KVM   Resume from specific stage
  sudo ./install.sh --self-test        Test framework internals
        """
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--resume", action="store_true",
                           help="Resume from last checkpoint")
    mode_group.add_argument("--repair", action="store_true",
                           help="Repair existing installation")
    mode_group.add_argument("--diagnose", action="store_true",
                           help="Run diagnostics only")
    mode_group.add_argument("--status", action="store_true",
                           help="Show installation status")
    mode_group.add_argument("--dry-run", action="store_true",
                           help="Preview what would be done")
    mode_group.add_argument("--preflight", action="store_true",
                           help="Run preflight checks only")
    mode_group.add_argument("--self-test", action="store_true",
                           help="Run framework self-tests")
    mode_group.add_argument("--clean-install", "--clean", action="store_true",
                           help="Wipe previous installation, VM, services, and state, then perform a fresh installation")
    mode_group.add_argument("--uninstall", action="store_true",
                           help="Uninstall CAPE resources created by this tool")
    mode_group.add_argument("--update", action="store_true",
                           help="Update existing CAPEv2 installation")

    parser.add_argument("--non-interactive", action="store_true",
                       help="Suppress interactive prompts")
    parser.add_argument("--from-stage", type=str, metavar="STAGE",
                       help="Resume from a specific stage")
    parser.add_argument("--reset-failed", action="store_true",
                       help="Reset failed stage state and retry")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config.toml")
    parser.add_argument("--log-level", type=str, default=None,
                       choices=["DEBUG", "INFO", "WARN", "ERROR"],
                       help="Override log level")
    parser.add_argument("--drift", action="store_true",
                       help="Show configuration drift (with --status)")
    parser.add_argument("--watch", action="store_true",
                       help="Continuous monitoring mode (with --diagnose)")

    parser.add_argument("--windows-edition", type=normalize_windows_edition,
                        help="Windows Enterprise Evaluation edition (win10_eval or win11_eval)")
    parser.add_argument("--auto-download-iso", action="store_true",
                        help="Automatically download official Microsoft Windows Enterprise Evaluation ISO")

    # Uninstall options
    parser.add_argument("--keep-cape-user", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--keep-vm", action="store_true")
    parser.add_argument("--full-reset", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Determine config path
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = args.config or os.environ.get("CAPE_CONFIG") or os.path.join(script_dir, "config.toml")

    # Load configuration
    try:
        config = Config(config_path, script_dir)
    except Exception as e:
        print(f"[ERROR] Failed to load configuration: {e}", file=sys.stderr)
        return 1

    # Apply CLI overrides
    if args.windows_edition:
        config.set("guest.windows_edition", args.windows_edition)
    if args.auto_download_iso:
        config.set("guest.auto_download_iso", True)

    # Setup logging
    log_level = args.log_level or os.environ.get("CAPE_LOG_LEVEL") or config.get("logging.level", "INFO")
    setup_logging(
        log_dir=os.path.join(script_dir, "logs"),
        level=log_level,
        redact=config.get("logging.redact_secrets", True)
    )
    logger = get_logger("cli")

    # Override non-interactive
    if args.non_interactive:
        config.set("installation.non_interactive", True)

    # Create orchestrator
    orchestrator = Orchestrator(config=config, project_dir=script_dir)

    try:
        if args.self_test:
            return orchestrator.self_test()
        elif args.preflight:
            return orchestrator.preflight()
        elif args.dry_run:
            return orchestrator.dry_run()
        elif args.diagnose:
            return orchestrator.diagnose(watch=args.watch)
        elif args.status:
            return orchestrator.status(drift=args.drift)
        elif args.repair:
            return orchestrator.repair()
        elif args.resume:
            return orchestrator.resume()
        elif args.clean_install:
            return orchestrator.clean_install()
        elif args.uninstall:
            return orchestrator.uninstall(
                keep_user=args.keep_cape_user,
                keep_data=args.keep_data,
                keep_vm=args.keep_vm,
                full_reset=args.full_reset,
                dry_run=False
            )
        elif args.update:
            return orchestrator.update()
        elif args.from_stage:
            return orchestrator.install(from_stage=args.from_stage)
        elif args.reset_failed:
            return orchestrator.reset_failed_and_retry()
        else:
            # Full installation
            return orchestrator.install()

    except RebootRequired as e:
        logger.warning(f"Reboot required: {e}")
        return 42
    except ManualInterventionRequired as e:
        logger.warning(f"Manual intervention required: {e}")
        return 43
    except PreflightError as e:
        logger.error(f"Preflight failed: {e}")
        return 2
    except CapeAutoError as e:
        logger.error(f"Installation error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
