![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Proxmox VE](https://img.shields.io/badge/Proxmox-VE-orange?logo=proxmox&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# pve-restore-watcher

Monitor active Proxmox restore tasks (`qmrestore` for VMs, `vzrestore` for LXC containers) with a tqdm-style progress dashboard and ETA. No external dependencies.

## Features

| Feature | Description |
| ------- | ----------- |
| Auto-detection | Finds active restore tasks from `/var/log/pve/tasks/active` |
| Live progress bar | tqdm-style display with current and average throughput |
| ETA | Smoothed speed estimation with remaining time |
| Every size unit | Handles the full `B` to `PiB` range Proxmox renders |
| Long restores | Parses durations past the hour and day marks (`2h 5m 3s`, `1d 2h`) |
| Responsive layout | Fits the terminal width, dropping the least useful field before wrapping |
| Log tail | Last 5 log lines shown below the progress bar |
| Color output | ANSI colors when running in a TTY |
| Debug mode | `--debug` flag for verbose diagnostics on stderr |

## Installation

Requires Python 3.10+. No external dependencies.

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

## Development

```bash
cd proxmox/restore-watcher
uv sync --extra test
uv run pytest -q
```

## Notes

Runs **on the Proxmox node itself**: it reads the task logs under `/var/log/pve/tasks/`, which are only readable by `root`.

Monitoring ends on the worker epilogue (`TASK OK`, `TASK ERROR:` or `TASK WARNINGS:`). Lines that merely mention success or failure partway through a restore are deliberately ignored, since they used to stop the dashboard on a task that was still running.

## Limitations

- Progress parsing is tied to Proxmox log line formats and may break on future PVE versions
- Some restore workflows expose only partial data (percentage without total size), making byte-level progress unavailable
- ETA is not shown when total size is not reported in the log
- Monitoring stops automatically after 10 minutes of log inactivity

## Related tools

- [`proxmox/disk-move-watcher`](../disk-move-watcher/README.md) for `qm move-disk` and `pct move-volume`
- [`proxmox/migration-watcher`](../migration-watcher/README.md) for live migrations

## License

MIT
