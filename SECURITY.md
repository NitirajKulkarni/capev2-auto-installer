# Security Policy

## Reporting Security Issues

Security is critical when dealing with automated malware analysis sandboxes.

If you discover a security vulnerability in this project, please **do not open a public issue**. Instead, report it directly to the maintainer:

- **Lead Author & Maintainer**: Nitiraj Kulkarni
- **Subject**: `[SECURITY VULNERABILITY] CAPEv2 Automated Installer`

Please include:
1. Detailed description of the vulnerability.
2. Steps to reproduce or proof-of-concept.
3. Potential impact on the host system or network.

## Sandbox Isolation Guarantees

By default, the installer enforces:
- **Network Isolation**: The analysis bridge (`virbr-cape`) is configured in isolated mode without public internet forwarding unless explicitly enabled in `config.toml`.
- **Privilege Separation**: CAPE runs under an unprivileged system user (`cape`), while only the minimal rooter helper (`cape-rooter.service`) handles privileged firewall operations.
- **Secret Redaction**: Passwords, API tokens, and database credentials are automatically redacted from all terminal outputs and log files.
