![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Proxmox VE](https://img.shields.io/badge/Proxmox-VE-orange?logo=proxmox&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# pve-disk-move-watcher

Monitor active Proxmox disk move tasks (`qm move-disk` / `pct move-volume`) with a tqdm-style progress dashboard and ETA. No external dependencies.

## Features

| Feature | Description |
| ------- | ----------- |
| Auto-detection | Finds active `qmmove` and `move_volume` tasks from `/var/log/pve/tasks/active` |
| Both transfer paths | Handles the offline `qemu-img convert` output and the online block-job mirror output |
| Live progress bar | tqdm-style display with current and average throughput |
| ETA | Smoothed speed estimation with remaining time |
| Multi-drive aware | Resets speed and ETA when the task moves on to the next drive |
| Responsive layout | Fits the terminal width, dropping the least useful field before wrapping |
| Log tail | Last 5 log lines shown below the progress bar |
| Color output | ANSI colors when running in a TTY |
| Task selection | `--list` to enumerate candidates, `--upid` to pick one explicitly |

## Requirements

Runs **on the Proxmox node itself**: it reads the task logs under `/var/log/pve/tasks/`, which are only readable by `root`. Python 3.10+, no external dependencies.

## Installation

### Using uv (recommended)

```bash
uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/disk-move-watcher'
```

### Using pipx

```bash
pipx install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/disk-move-watcher'
```

### From a local clone

```bash
cd proxmox/disk-move-watcher
uv tool install .
# or: pipx install .
```

## Usage

```bash
pve-disk-move-watcher
```

The tool reads `/var/log/pve/tasks/active`, picks the most recent disk move task, and streams a live dashboard until the task completes or you press `Ctrl+C`:

```text
Monitoring disk move task: qmmove vmid=123 node=burns upid=UPID:burns:...
Log file: /var/log/pve/tasks/4/UPID:burns:...
mirror-scsi0 [====================....]  85.1% | 172.20/202.30 GiB | Now  102.4 MiB/s | Avg   55.1 MiB/s | Elapsed 00:53:20 | ETA 00:05:01
  mirror-scsi0: transferred 172.2 GiB of 202.3 GiB (85.12%) in 53m 21s
```

When several moves run at once, list them and target one:

```bash
pve-disk-move-watcher --list
pve-disk-move-watcher --upid 'UPID:burns:00006472:170DD2EE:6A7B4794:qmmove:123:root@pam:'
```

### Options

| Flag | Description |
| ---- | ----------- |
| `--list` | List active disk move tasks and exit |
| `--upid UPID` | Monitor this exact UPID instead of auto-selecting |
| `--debug` | Enable verbose debug logs on stderr |

## How it works

1. Parses `/var/log/pve/tasks/active` and keeps the tasks whose worker type is `qmmove` (VM disk move) or `move_volume` (LXC volume move).
2. Resolves the task log file. Proxmox shards these logs into 16 folders keyed on the **last** hex digit of the UPID's starttime field, matching `substr($starttime, 7, 1)` in `PVE::RESTEnvironment::fork_worker`.
3. Follows the log and parses the transfer counters. Online moves report their own elapsed time (`in 1m 31s`); offline moves report none, so samples are stamped from the monotonic clock.
4. Stops on `TASK OK`, `TASK ERROR:` or `TASK WARNINGS:`, and prints a one-line final status.

## Limitations

- **LXC volume moves show no percentage.** `pct move-volume` copies data with `rsync` invoked without `--progress`, so Proxmox writes no incremental counters to the task log — only a final `--stats` block. The dashboard falls back to the log tail for those tasks.
- Reassigning a disk to another guest (`qm move-disk --target-vmid`) copies no data, so there is nothing to plot.
- Progress parsing is tied to Proxmox log line formats and may break on future PVE versions.
- ETA is not shown until two progress samples are known.
- Monitoring stops automatically after 10 minutes of log inactivity.

## Development

```bash
cd proxmox/disk-move-watcher
uv sync --extra test
uv run pytest -q
```

## License

MIT
