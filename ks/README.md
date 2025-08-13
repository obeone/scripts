# ks-debug-helper 🚀

A command-line utility to quickly launch a privileged debug container targeting a pod in your Kubernetes cluster.

This tool simplifies the process of debugging applications running in Kubernetes by providing an interactive way to select the target pod and container, and then automatically launching a debug session.

## Features

- **Interactive Selection**: Uses `fzf` for quick, interactive selection of Kubernetes context, namespace, pod, and container.
- **Customizable Debug Image**: Specify your preferred debug image using the `--image` option. Defaults to a sensible choice with common networking and troubleshooting tools.
- **Automatic `kubectl` Command Generation**: Generates and executes the appropriate `kubectl debug` command for you.
- **Dry-Run Mode**: Use `--dry-run` to print the `kubectl` command without executing it, perfect for learning or scripting.
- **Colored Logging**: Provides clear, colored log output with adjustable verbosity (`--log-level`).
- **Security Profile Management**:
  - Automatically applies the `privileged` Pod Security Admission label to the target namespace if required, and cleans it up on exit.
  - Allows specifying a security profile with `--profile` (or the `KS_DEBUG_PROFILE` environment variable).
- **Shell Completion**: Generates completion scripts for Bash, Zsh, and Fish shells for an enhanced user experience.

## Prerequisites

Before using `ks-debug-helper`, you need the following tools installed and available in your system's `PATH`:

- **`kubectl`**: The Kubernetes command-line tool.
- **`fzf`**: A command-line fuzzy finder, used for interactive menus.

## Installation

It is recommended to install the tool using `pipx` to ensure it is isolated in its own environment.

```bash
# Clone the repository if you haven't already
# git clone https://github.com/obeone/scripts
# cd scripts

# Install using pipx
pipx install ./ks

# or
uv tool install ./ks
```

After installation, you may need to set up shell completion.

### Shell Completion Setup

To enable command-line completion, add the appropriate line to your shell's configuration file (e.g., `.bashrc`, `.zshrc`, `.config/fish/config.fish`).

**Bash:**

```bash
eval "$(ks --completion bash)"
```

**Zsh:**

```bash
eval "$(ks --completion zsh)"
```

**Fish:**

```bash

ks --completion fish | source
```

## Usage

### Basic Usage

The simplest way to use the tool is to run it without arguments. It will guide you through selecting the context, namespace, pod, and container.

```bash
ks
```

You can also specify the target directly using command-line options:

```bash
ks -n my-namespace -p my-app-pod-xxxx -c app-container
```

### Advanced Examples

**Using a custom debug image:**

```bash
ks --image obeoneorg/netshoot
```

**Specifying a context and namespace:**

```bash
ks --context my-cluster-context -n my-special-namespace
```

**Dry-run to see the generated command:**

```bash
ks -n my-namespace -p my-pod --dry-run
```

**Setting the log level for more detailed output:**

```bash
ks --log-level debug
```

By default, the debug container runs with the `sysadmin` profile, granting extensive privileges. You can override this via the `--profile` option or the `KS_DEBUG_PROFILE` environment variable.

Run `ks --help` for a full list of all available options.
