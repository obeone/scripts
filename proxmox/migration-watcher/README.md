# Proxmox Migration Watcher

A command-line tool to monitor Proxmox QEMU migration progress with a text-based transfer speed graph.

## Description

This tool connects to the Proxmox task logs (`/var/log/pve/tasks/`) to find active QEMU migration tasks. It then follows the log file for the selected task, parses the progress updates, calculates the transfer speed and estimated time of arrival (ETA), and displays this information in a dynamic command-line interface. A key feature is the text-based graph showing the historical transfer speed using the `plotext` library.

It is designed to provide a more detailed and visual overview of ongoing migrations than the standard Proxmox CLI output.

## Features

* Automatically detects active QEMU migration tasks.
* Allows selection of a specific task if multiple are running.
* Displays current progress (transferred/total GiB, percentage).
* Calculates and displays current transfer speed (MiB/s).
* Calculates and displays Estimated Time of Arrival (ETA).
* Provides a real-time text-based graph of transfer speed history.
* Shows recent log entries from the task log.
* Updates the display in place using ANSI escape codes.

## Installation

This tool requires Python 3.7 or higher. It is recommended to install it in an isolated environment using `pipx` or `uv`.

### Using pipx (Recommended)

`pipx` installs Python applications into isolated environments to avoid dependency conflicts.

1. Ensure you have `pipx` installed. If not, [follow the instructions](https://pypa.io/stable/installation/#pipx).
2. Install the tool:

    ```bash
    pipx install .
    ```

    (Run this command from the `proxmox/migration-watcher/` directory)

3. Alternatively, install directly from the Git repository URL:

    ```bash
    pipx install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/migration-watcher'
    ```

### Using uv

`uv` is a fast Python package installer and manager.

1. Ensure you have `uv` installed. If not, [follow the instructions](https://github.com/astral-sh/uv#installation).
2. Install the tool:

    ```bash
    uv tool install .
    ```

    (Run this command from the `proxmox/migration-watcher/` directory)

3. Alternatively, install directly from the Git repository URL:

    ```bash
    uv tool install 'https://github.com/obeone/scripts.git#subdirectory=proxmox/migration-watcher'
    ```

### Classic Method (using venv and pip)

You can also install it in a standard Python virtual environment.

1. Navigate to the project directory:

    ```bash
    cd proxmox/migration-watcher/
    ```

2. Create a virtual environment:

    ```bash
    python -m venv .venv
    ```

3. Activate the virtual environment:
    * On Linux/macOS:

        ```bash
        source .venv/bin/activate
        ```

    * On Windows:

        ```bash
        .venv\Scripts\activate
        ```

4. Install the tool and its dependencies:

    ```bash
    pip install .
    ```

## Usage

Once installed (via `pipx`, `uv`, or activated in a `venv`), run the tool using the console script name defined in `pyproject.toml`:

```bash
pve-migration-watcher
```

The tool will list active `qmigrate` tasks and prompt you to select one if multiple are running. It will then start monitoring the selected task's log file and display the progress.

Press `Ctrl+C` to stop monitoring.

## Requirements

* Python 3.7 or higher
* Access to Proxmox task logs (`/var/log/pve/tasks/`). This typically means running the tool on a Proxmox node or having appropriate permissions and access to the filesystem.
* `plotext` Python library (installed automatically by the installation methods above).

## Development

If you want to contribute or modify the code:

1. Clone the repository.
2. Navigate to the `proxmox/migration-watcher/` directory.
3. Set up a development environment (e.g., using `venv` or `uv venv`).
4. Install the project in editable mode:
    * Using `pip`: `pip install -e .`
    * Using `uv`: `uv pip install -e .`

## License

This project is licensed under the MIT License. See the `LICENSE` file (if present) or the `pyproject.toml` for details.
