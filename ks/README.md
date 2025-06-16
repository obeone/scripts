# ks-debug-helper 🚀

A command line utility to quickly launch a privileged debug container targeting a pod in your Kubernetes cluster.

## Features

- Interactive selection of context, namespace, pod and container via **fzf**
- Customizable debug image (`--image` option)
- Generates and runs the appropriate `kubectl debug` command
- Optional dry-run mode to only print the command
- Colored logging with adjustable level
- Configurable security profile via `--profile` option or `KS_DEBUG_PROFILE` environment variable

## Installation

```bash
pipx install ./ks
```

## Usage

```bash
ks -n my-namespace -p my-pod -c app-container
```

By default, the debug container runs with the `sysadmin` profile, granting root privileges. You can override this via `--profile` or the `KS_DEBUG_PROFILE` environment variable.

Run `ks --help` for all options.
