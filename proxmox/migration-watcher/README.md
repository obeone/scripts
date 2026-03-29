![Python](https://img.shields.io/badge/Python-3.7+-blue?logo=python&logoColor=white)
![Proxmox VE](https://img.shields.io/badge/Proxmox-VE-orange?logo=proxmox&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# pve-migration-watcher

Monitor Proxmox QEMU live migrations with a real-time transfer speed graph and ETA.

```mermaid
flowchart TB
    A[Read /var/log/pve/tasks/active] --> B[Detect active qmigrate tasks]
    B --> C{Multiple tasks?}
    C -- Yes --> D[Prompt user to select]
    C -- No --> E[Auto-select]
    D --> F[Follow task log file]
    E --> F
    F --> G[Parse progress updates]
    G --> H[Display speed graph + ETA]
    H --> F
```

## Features

| Feature | Description |
| ------- | ----------- |
| Auto-detection | Finds all active QEMU migration tasks from Proxmox task logs |
| Task selection | Prompts when multiple migrations are running simultaneously |
| Progress display | Transferred / total (GiB), percentage complete |
| Speed graph | Real-time text-based transfer speed history via `plotext` |
| ETA | Estimated time to completion based on current speed |
| Log tail | Recent raw log lines shown below the graph |
| In-place updates | ANSI escape codes keep the display clean and non-scrolling |

## Installation

Requires Python 3.7+. Must be run on a Proxmox node (or with filesystem access to `/var/log/pve/tasks/`).

### Using uv (recommended)

```bash
uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/migration-watcher'
```

### Using pipx

```bash
pipx install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/migration-watcher'
```

### From a local clone

```bash
cd proxmox/migration-watcher
uv tool install .
# or: pipx install .
```

## Usage

```bash
pve-migration-watcher
```

The tool detects active migrations, lets you pick one if several are running, then streams live progress until the migration completes or you press `Ctrl+C`.

## Requirements

- Python 3.7+
- `plotext` (installed automatically)
- Read access to `/var/log/pve/tasks/` — run on a Proxmox node

## License

MIT
