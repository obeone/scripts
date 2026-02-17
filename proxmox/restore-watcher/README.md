# Proxmox Restore Watcher

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A command-line tool to monitor active Proxmox restore tasks (`qmrestore`, `pctrestore`) with a live tqdm-like progress dashboard.

## 🚀 Features

| Feature | Description |
| ------- | ----------- |
| 🔍 Auto-detection | Finds active restore tasks from `/var/log/pve/tasks/active` |
| 📊 Live dashboard | tqdm-style progress bar with current and average throughput |
| ⏱️ ETA calculation | Smoothed speed estimation with remaining time display |
| 📝 Log tail | Shows the 5 most recent log lines below the progress bar |
| 🎨 Color output | ANSI-colored output when running in a TTY |
| 🐛 Debug mode | Optional `--debug` flag for verbose diagnostics on stderr |

## 📦 Installation

### Using uv (Recommended)

```bash
uv tool install .
```

(Run from the `proxmox/restore-watcher/` directory)

Or directly from the Git repository:

```bash
uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/restore-watcher'
```

### Using pipx

```bash
pipx install .
```

### For development

```bash
uv venv
source .venv/bin/activate
uv pip install -e .[test]
```

## 🔧 Usage

```bash
pve-restore-watcher
```

The tool will:

1. Read `/var/log/pve/tasks/active` to find running tasks
2. Filter for restore-like operations (qmrestore, pctrestore, or tasks containing restore keywords)
3. Resolve and follow the selected task's log file
4. Display a live progress dashboard until the task completes

Press `Ctrl+C` to stop monitoring.

### Options

| Flag | Description |
| ---- | ----------- |
| `--debug` | Enable debug logs on stderr |

## ⚙️ Requirements

- Python 3.8+
- Access to `/var/log/pve/tasks/` (run on a Proxmox node)
- Permission to read task log files

## ⚠️ Limitations

- Progress parsing depends on Proxmox log line formats
- Some restore workflows expose only partial progress data (percent without total size)
- ETA is unavailable when total size is not reported
- If no new log data appears for 10 minutes, monitoring stops automatically

## 🧪 Tests

```bash
uv run pytest -v
```

## 📄 License

MIT
