# Scripts Collection

A set of small Python utilities grouped in a single repository. Each subproject lives in its own directory and can be installed individually.

| Project | Description |
| ------- | ----------- |
| [ks](ks/README.md) | Kubernetes debug helper to spawn a privileged container in your pods. |
| [openai-usage](openai-usage/README.md) | Command line tool to inspect OpenAI API usage and cost. |
| [proxmox](proxmox/README.md) | Utilities for Proxmox VE including a migration watcher. |
| [slideshow](slideshow/README.md) | Tkinter based image slideshow application. |

## Installing a Tool

All subprojects are Python packages with a `pyproject.toml`. You can install any of them with `pipx` (recommended):

```bash
pipx install ./<project>
```

For example, to install `ks`:

```bash
pipx install ./ks
```

Each project has more detailed instructions in its own README.

## Development

Clone the repository and navigate to the subproject you want to work on. Create a virtual environment and install the package in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Happy hacking!
