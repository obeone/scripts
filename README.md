# 🛠️ Scripts Collection 🐍

A curated collection of small, powerful Python utilities, all neatly organized in a single repository. Each subproject is designed to be self-contained and can be installed individually to suit your needs.

---

## 🚀 Projects

| Project | Description |
| ------- | ----------- |
| 🐳 [**docker-kubernetes**](docker-kubernetes/README.md) | A wrapper for `docker` to automatically expose ports on a Kubernetes service when running Docker-in-Kubernetes (DinD). |
| 🐛 [**ks**](ks/README.md) | Your friendly Kubernetes debugging assistant. It helps you spawn a privileged container directly in your pods for easy troubleshooting. |
| 📊 [**openai-usage**](openai-usage/README.md) | A command-line tool to inspect OpenAI API token usage and estimate costs. |
| 🖥️ [**proxmox**](proxmox/README.md) | Proxmox VE utilities: migration watcher (live migration progress) and restore watcher (restore task monitoring). |
| 🖼️ [**slideshow**](slideshow/README.md) | A simple yet elegant image slideshow application built with Tkinter. |
| 🚀 [**transfer.sh**](transfer.sh/README.md) | A powerful command-line tool for [transfer.sh](https://transfer.sh). |

---

## 📦 Installation

Most tools are packaged with `pyproject.toml` and can be installed directly from GitHub using [`uv`](https://github.com/astral-sh/uv) — no need to clone the repository.

### Install directly from GitHub with uv (Recommended)

```bash
uv tool install 'https://github.com/obeone/scripts.git#subdirectory=<project_directory>'
```

For example:

| Tool | Command |
| ---- | ------- |
| ks | `uv tool install 'https://github.com/obeone/scripts.git#subdirectory=ks'` |
| openai-usage | `uv tool install 'https://github.com/obeone/scripts.git#subdirectory=openai-usage'` |
| pve-migration-watcher | `uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/migration-watcher'` |
| pve-restore-watcher | `uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/restore-watcher'` |
| slideshow | `uv tool install 'https://github.com/obeone/scripts.git#subdirectory=slideshow'` |

### From a local clone

```bash
git clone https://github.com/obeone/scripts.git
uv tool install ./scripts/<project_directory>
```

### Using pipx

`pipx` works the same way if you prefer it over `uv`:

```bash
pipx install 'https://github.com/obeone/scripts.git#subdirectory=<project_directory>'
```

> **Note**: For non-Python projects like `docker-kubernetes` or `transfer.sh`, refer to their specific `README.md` for installation instructions.

---

## 💻 Development

1. **Clone the repository:**

    ```bash
    git clone https://github.com/obeone/scripts.git
    cd scripts
    ```

2. **Navigate to a subproject:**

    ```bash
    cd <project_directory>
    ```

3. **Set up a virtual environment and install in editable mode:**

    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install -e .
    ```

Happy hacking! 🎉
