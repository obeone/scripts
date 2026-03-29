![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![Proxmox VE](https://img.shields.io/badge/Proxmox-VE-orange?logo=proxmox&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# pve-restore-watcher

Monitor active Proxmox restore tasks (`qmrestore`/`pctrestore`) with a tqdm-style progress dashboard and ETA. No external dependencies.

## Features

| Feature | Description |
| ------- | ----------- |
| Auto-detection | Finds active restore tasks from `/var/log/pve/tasks/active` |
| Live progress bar | tqdm-style display with current and average throughput |
| ETA | Smoothed speed estimation with remaining time |
| Log tail | Last 5 log lines shown below the progress bar |
| Color output | ANSI colors when running in a TTY |
| Debug mode | `--debug` flag for verbose diagnostics on stderr |

## Installation

Requires Python 3.8+. No external dependencies.

### Using uv (recommended)

```bash
uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/restore-watcher'
```

### Using pipx

```bash
pipx install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/restore-watcher'
```

### From a local clone

```bash
cd proxmox/restore-watcher
uv tool install .
# or: pipx install .
```

## Usage

```bash
pve-restore-watcher
```

The tool reads `/var/log/pve/tasks/active`, filters for restore operations, and streams a live dashboard until the task completes or you press `Ctrl+C`.

### Options

| Flag | Description |
| ---- | ----------- |
| `--debug` | Enable verbose debug logs on stderr |

## Limitations

- Progress parsing is tied to Proxmox log line formats — may break on future PVE versions
- Some restore workflows expose only partial data (percentage without total size), making byte-level progress unavailable
- ETA is not shown when total size is not reported in the log
- Monitoring stops automatically after 10 minutes of log inactivity

## License

MIT
