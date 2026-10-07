# CAPEv2 Operator Runbook

This runbook describes operational procedures for maintaining, updating, diagnosing, and repairing a CAPEv2 installation managed by this framework.

---

## 1. Daily Health Inspection

To check the operational status of all CAPEv2 components:

```bash
sudo ./status.sh
```

To run active health probes across KVM, libvirt, database, and CAPE services:

```bash
sudo ./diagnose.sh
```

For continuous monitoring (auto-refreshing every 5 seconds):

```bash
sudo ./diagnose.sh --watch
```

---

## 2. Service Management

The systemd services managed by CAPE are:
- `cape.service`: Core sandbox orchestrator and task dispatcher
- `cape-web.service`: Django web UI and API
- `cape-processor.service`: Analysis result processing and report generation
- `cape-rooter.service`: Privileged network routing daemon

### Restarting all CAPE services
```bash
sudo systemctl restart cape-rooter cape cape-processor cape-web
```

### Viewing logs
```bash
# Main cuckoo service
journalctl -u cape.service -f

# Web service
journalctl -u cape-web.service -f

# Rooter helper
journalctl -u cape-rooter.service -f
```

---

## 3. Repairing a Degraded Installation

If any service becomes unresponsive or after an unclean host reboot:

```bash
sudo ./repair.sh
```

The repair tool will:
1. Reload systemd daemon units
2. Verify libvirt socket and bridge interfaces
3. Restart failed units in their proper dependency order
4. Verify HTTP endpoints for web UI (port 8000) and rooter sockets

---

## 4. Updating CAPEv2 to Latest Upstream

To pull the latest updates from the upstream CAPEv2 repository and refresh the environment:

```bash
sudo ./install.sh --update
```

This procedure:
1. Backs up existing custom configurations (`custom/conf/*.conf`)
2. Pulls git commits from upstream `master`
3. Updates Python virtual environment dependencies
4. Applies any new database migrations
5. Restarts CAPE systemd services
6. Verifies system health

---

## 5. Clean Uninstallation

To remove CAPE resources without affecting other workloads:

```bash
# Safely uninstalls installer-created systemd services and configurations
sudo ./uninstall.sh

# Complete reset including VMs and data directories
sudo ./uninstall.sh --full-reset
```
