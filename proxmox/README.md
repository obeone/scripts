![Python](https://img.shields.io/badge/Python-3.7+-blue?logo=python&logoColor=white)
![Proxmox VE](https://img.shields.io/badge/Proxmox-VE-orange?logo=proxmox&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# Proxmox Tools

CLI utilities for monitoring Proxmox VE operations in real time.

## Tools

| Tool | Description |
| ---- | ----------- |
| [migration-watcher](migration-watcher/README.md) | Monitor QEMU live migrations with a real-time transfer speed graph and ETA |
| [restore-watcher](restore-watcher/README.md) | Monitor active restore tasks (`qmrestore`/`pctrestore`) with a tqdm-style progress dashboard |

Each tool installs independently via `uv` or `pipx`. Must be run on a Proxmox node with access to `/var/log/pve/tasks/`.
