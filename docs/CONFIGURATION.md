# CAPEv2 Installer Configuration Reference (`config.toml`)

The installer is configured via `config.toml` located in the root directory.

---

## `[installation]` Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cape_root` | string | `"/opt/CAPEv2"` | Destination directory for the CAPEv2 source and virtualenv. |
| `cape_user` | string | `"cape"` | System service account created to run CAPE services. |
| `cape_repo` | string | `"https://github.com/kevoreilly/CAPEv2.git"` | Upstream git repository. |
| `cape_ref` | string | `"master"` | Git branch, tag, or commit SHA to check out. |
| `install_profile` | string | `"all"` | Installation profile: `all`, `base`, `sandbox`, `dependencies`. |
| `python_manager` | string | `"auto"` | Python package manager to use: `auto`, `poetry`, `uv`. |
| `non_interactive` | bool | `true` | When true, runs without interactive prompts. |
| `auto_repair` | bool | `true` | When true, attempts automated repairs on stage failure. |
| `max_repair_attempts` | int | `3` | Maximum automated repair attempts per stage before asking for intervention. |

---

## `[safety]` Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allow_host_network_changes` | bool | `false` | Whether the installer is permitted to modify host physical interfaces. |
| `allow_internet_routing` | bool | `false` | Whether to route guest analysis traffic to the public Internet. |
| `allow_firewall_changes` | bool | `true` | Allows creating UFW / iptables rules for the analysis bridge. |
| `allow_reboot` | bool | `false` | Allows the installer to reboot the host when a kernel or group change requires it. |
| `preserve_existing_libvirt_vms` | bool | `true` | Guarantees existing VMs not created by this installer are never touched. |
| `preserve_existing_networks` | bool | `true` | Guarantees existing libvirt networks are preserved. |
| `destructive_repair` | bool | `false` | Allows high-risk remediation actions (disabled by default). |
| `remote_safe_mode` | string | `"auto"` | Auto-detects SSH sessions and enables protections. |

---

## `[network]` Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"isolated"` | Analysis network isolation mode: `isolated`, `nat`, `internet`. |
| `subnet` | string | `"192.168.250.0/24"` | Subnet allocated for the sandbox analysis network. |
| `gateway` | string | `"192.168.250.1"` | Gateway IP assigned to the host bridge interface. |
| `vm_ip_start` | string | `"192.168.250.100"`| Starting IP address for sandbox virtual machines. |
| `dns` | string | `"none"` | Guest DNS resolution mode: `none`, `host`, or explicit IP. |
| `libvirt_network_name`| string | `"cape-analysis"`| Name of the libvirt isolated network. |
| `cape_interface` | string | `"virbr1"` | Interface name used for packet capture / sniffing. |
| `web_bind` | string | `"127.0.0.1"` | IP address for binding the Django web interface. |
| `web_port` | int | `8000` | Port for the Django web interface. |

---

## `[guest]` Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | `true` | Enable automated Windows VM creation. |
| `name` | string | `"cape-win"` | Libvirt domain name for the analysis machine. |
| `platform` | string | `"windows"` | Guest operating system family. |
| `iso_path` | string | `""` | Absolute path to Windows installer ISO. If empty, VM provisioning is safely skipped. |
| `disk_path` | string | `"/var/lib/libvirt/images/cape-win.qcow2"` | Path for the virtual disk image. |
| `disk_size_gb` | int | `80` | Size of the virtual disk in gigabytes. |
| `memory_mb` | int | `8192` | Virtual RAM in megabytes. |
| `vcpus` | int | `4` | Virtual CPU cores allocated to the guest. |
| `snapshot_name` | string | `"cape-clean"` | Name of the clean snapshot restored before each analysis. |

---

## `[database]` Section

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | string | `"auto"` | Database backend: `auto`, `mongodb`, `postgresql`. |
| `mongodb_host` | string | `"127.0.0.1"` | Host address for MongoDB connection. |
| `mongodb_port` | int | `27017` | Port for MongoDB. |
| `postgresql_host` | string | `"127.0.0.1"` | Host address for PostgreSQL connection. |
| `postgresql_port` | int | `5432` | Port for PostgreSQL. |
| `postgresql_db` | string | `"cape"` | Database name. |
