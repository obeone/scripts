# Docker-Kube Script

A wrapper script to simplify running Docker commands in a Kubernetes context, automatically managing Kubernetes service ports based on Docker's published ports.

## Table of Contents

- [Docker-Kube Script](#docker-kube-script)
  - [Table of Contents](#table-of-contents)
  - [Description](#description)
  - [Core Use Case: Docker-in-Kubernetes](#core-use-case-docker-in-kubernetes)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Usage](#usage)
  - [How It Works](#how-it-works)
    - [Port Detection](#port-detection)
    - [Kubernetes Service Management](#kubernetes-service-management)
  - [Configuration](#configuration)
  - [Examples](#examples)
    - [Using `docker run`](#using-docker-run)
    - [Using `docker compose`](#using-docker-compose)
  - [Author](#author)
  - [License](#license)

## Description

This script, `docker-kube.sh`, is a wrapper around the `docker` command designed to simplify port management when running a **Docker daemon inside a Kubernetes pod**.

When you use a Docker-in-Kubernetes setup, containers you create with `docker run` or `docker compose` are siblings to the Docker daemon pod, all running on the same Kubernetes node. To access these containers from outside the cluster, you must expose their ports through a Kubernetes service (e.g., a `LoadBalancer` or `NodePort` service) that targets the Docker daemon pod.

This script automates that process. When you run a command like `docker run -p 8080:80`, it automatically:

1. Parses the command to find the host port (`8080`).
2. Adds this port to a pre-configured Kubernetes service.
3. Executes the original `docker` command against the in-cluster Docker daemon.

This eliminates the need to manually edit Kubernetes service manifests every time you want to expose a new container port, streamlining development workflows in a Docker-in-Kubernetes environment.

## Core Use Case: Docker-in-Kubernetes

The primary scenario for this script is when you have deployed a Docker engine as a pod within your Kubernetes cluster and configured your local Docker CLI to use it as a context.

This setup allows you to use familiar `docker` and `docker-compose` commands to run containers directly within your cluster's network, benefiting from its resources and environment. The `docker-kube.sh` script is the missing link that makes network exposition seamless.

## Prerequisites

Before using this script, ensure you have the following tools installed and available in your `PATH`:

- **`docker`**: The Docker CLI.
- **`kubectl`**: The Kubernetes command-line tool, configured to connect to your cluster.
- **`jq`**: A lightweight and flexible command-line JSON processor.
- **`yq`**: A command-line YAML processor (used for parsing Docker Compose files).

## Installation

1. **Clone the repository or download the script:**

    ```bash
    git clone https://github.com/obeone/scripts
    cd scripts/docker-kubernetes
    ```

2. **Make the script executable:**

    ```bash
    chmod +x docker-kube.sh
    ```

3. **Create a symbolic link (Recommended):**
    To use `docker-kube.sh` as a direct replacement for `docker`, you can create a symlink to it from a directory in your `PATH`, or create an alias.

    **Symlink Example:**

    ```bash
    # Make sure /usr/local/bin is in your PATH
    sudo ln -s "$(pwd)/docker-kube.sh" /usr/local/bin/docker
    ```

    > **Warning:** This will replace the standard `docker` command. The script is designed to pass all arguments to the real Docker CLI, but use this with caution. A safer alternative is to name the symlink something else, like `dkr`.

    **Alias Example:**
    Add the following to your shell's configuration file (`~/.bashrc`, `~/.zshrc`, etc.):

    ```bash
    alias dkr="$(pwd)/docker-kube.sh"
    ```

    Then, use `dkr` instead of `docker`.

## Usage

Execute the script as you would the `docker` command. The script will automatically handle the port management and then execute the Docker command with the `--context kube` flag.

```bash
./docker-kube.sh [docker arguments]
```

**Example with `docker run`:**

```bash
./docker-kube.sh run -p 8080:80 --name my-web-server nginx
```

**Example with `docker compose`:**

```bash
# The script will automatically find 'compose.yaml' or 'docker-compose.yml'
./docker-kube.sh compose up -d
```

## How It Works

### Port Detection

The script detects which host ports to open through two main mechanisms:

1. **Command-line Arguments:** It parses the command-line arguments for `-p` or `--publish` flags to extract port mappings (e.g., `-p 8080:80`).
2. **Docker Compose Files:** If the command is `docker compose`, it uses `yq` to parse the Docker Compose file (e.g., `compose.yaml`) and extracts all published ports from the `ports` section of each service.

### Kubernetes Service Management

1. Once the list of required host ports is gathered, the script communicates with your Kubernetes cluster using `kubectl`.
2. It checks the configured Kubernetes service (default: `docker` in the `docker` namespace) to see if the ports are already exposed.
3. If a port is not exposed, the script uses `jq` to modify the service's JSON definition in-memory, adding the new port configuration.
4. Finally, it applies the updated service definition to the cluster using `kubectl apply`.

After ensuring all necessary ports are open on the service, it proceeds to execute the original Docker command, targeting the Kubernetes context.

## Configuration

The script's Kubernetes-related settings can be configured by modifying the following constants at the top of the `docker-kube.sh` file:

- `K8S_SERVICE_NAME`: The name of the Kubernetes service to manage. **Default:** `"docker"`
- `K8S_NAMESPACE`: The namespace where the service resides. **Default:** `"docker"`
- `K8S_DEFAULT_PROTOCOL`: The protocol to use for new ports. **Default:** `"TCP"`

## Examples

### Using `docker run`

Imagine you want to run a Caddy web server and expose it on port `8080`.

**Command:**

```bash
./docker-kube.sh run -d -p 8080:80 --name caddy caddy
```

**What happens:**

1. The script detects the `-p 8080:80` argument and identifies `8080` as the host port to manage.
2. It checks the `docker` service in the `docker` namespace.
3. If port `8080` is not already defined on the service, it adds it.
4. It executes `docker --context kube run -d -p 8080:80 --name caddy caddy`.

### Using `docker compose`

Consider a `compose.yaml` file like this:

**`compose.yaml`:**

```yaml
services:
  web:
    image: nginx
    ports:
      - "8081:80"
  api:
    image: my-api-image
    ports:
      - "9000:9000"
```

**Command:**

```bash
./docker-kube.sh compose up
```

**What happens:**

1. The script detects the `compose` command.
2. It parses `compose.yaml` and finds two host ports to manage: `8081` and `9000`.
3. It ensures both ports are open on the `docker` service in Kubernetes.
4. It executes `docker --context kube compose up`.

## Author

- **Grégoire Compagnon** - *Initial work* - [obeone](https://github.com/obeone)
- Contact: <obeone@obeone.org>

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
