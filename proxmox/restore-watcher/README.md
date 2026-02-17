# Proxmox Restore Watcher

CLI tool to monitor active Proxmox restore tasks from task logs.

## Installation

Using `uv` from this directory:

```bash
uv tool install .
```

For development and tests:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .[test]
```

## Usage

```bash
pve-restore-watcher
```

The command inspects `/var/log/pve/tasks/active`, filters restore-like tasks,
follows the selected task log, and prints progress metrics with a final status.

## Requirements

- Python 3.8+
- Access to `/var/log/pve/tasks/`
- Permission to read task log files on a Proxmox node

## Limitations

- Progress parsing depends on Proxmox log line formats.
- Some restore workflows expose only partial progress data.
- ETA is unavailable when total size is not reported.
