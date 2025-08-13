# 🛠️ Scripts Collection 🐍

A curated collection of small, powerful Python utilities, all neatly organized in a single repository. Each subproject is designed to be self-contained and can be installed individually to suit your needs.

---

## 🚀 Projects

Here's a glimpse of the tools you'll find inside:

| Project | Description |
| ------- | ----------- |
| 🐳 [**docker-kubernetes**](docker-kubernetes/README.md) | A wrapper for `docker` to automatically expose ports on a Kubernetes service when running Docker-in-Kubernetes (DinD). |
| 🐛 [**ks**](ks/README.md) | Your friendly Kubernetes debugging assistant. It helps you spawn a privileged container directly in your pods for easy troubleshooting. |
| 📊 [**openai-usage**](openai-usage/README.md) | A command-line tool to inspect OpenAI API token usage and estimate costs. |
| 🖥️ [**proxmox**](proxmox/README.md) | A set of utilities for Proxmox VE, including a nifty migration watcher to keep track of VM movements. |
| 🖼️ [**slideshow**](slideshow/README.md) | A simple yet elegant image slideshow application built with Tkinter. |
| 🚀 [**transfer.sh**](transfer.sh/README.md) | A powerful command-line tool for [transfer.sh](https://transfer.sh). |

---

## 📦 Installation

Most of these tools are packaged with `pyproject.toml` and can be installed seamlessly using `pipx` (the recommended way!).

To install a tool, simply run:

```bash
pipx install ./<project_directory>
```

For example, to get the `ks` helper up and running:

```bash
pipx install ./ks
```

✨ **Note**: For non-Python projects like `docker-kubernetes` or `transfer.sh`, please refer to the specific installation instructions in its own `README.md`. Each project's README contains more detailed information.

---

## 💻 Development

Ready to contribute or customize a script? Here’s how to get started:

1. **Clone the repository:**

    ```bash
    git clone https://github.com/obeone/scripts.git
    cd scripts
    ```

2. **Navigate to a subproject:**

    ```bash
    cd <project_directory>
    ```

3. **Set up a virtual environment:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

4. **Install in editable mode:**

    ```bash
    pip install -e .
    ```

Happy hacking! 🎉
