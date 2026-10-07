# Contributing to CAPEv2 Universal Automated Installer

Thank you for your interest in contributing! This project is maintained by **Nitiraj Kulkarni**.

## Code of Conduct

Please be respectful and constructive in all discussions, issues, and code reviews.

## Development Workflow

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/<your-username>/cape-auto-installer.git
   cd cape-auto-installer
   ```

2. **Branching**:
   Create a topic branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```

3. **Running Self-Tests**:
   Test the internal framework engines:
   ```bash
   python3 src/cape_auto/cli.py --self-test
   ```

4. **Running Unit Tests**:
   Ensure all automated tests pass:
   ```bash
   python3 -m unittest discover tests -v
   ```

5. **Dry-Run Validation**:
   Verify configuration and state planning:
   ```bash
   python3 src/cape_auto/cli.py --dry-run
   ```

## Design Principles

- **No Drama Principle**: Never crash on unexpected output; parse safely with defaults.
- **Strict Resource Ownership**: Never modify or remove resources not explicitly created by this installer.
- **Remote-Safe**: Always guard against breaking SSH connectivity when altering network/firewall configurations.
- **Portability**: Code must run without external pip packages on standard Python 3.10+.
