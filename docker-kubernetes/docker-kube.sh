#!/usr/bin/env bash

# Script constants for Kubernetes service management
readonly K8S_SERVICE_NAME="docker"
readonly K8S_NAMESPACE="docker"
readonly K8S_DEFAULT_PROTOCOL="TCP"

# --- Global state ---
# This array will be populated with host ports to open.
host_ports_to_open_list=()

################################################################################
# Finds the Docker Compose file to use.
# It first checks for -f or --file arguments. If not found, it searches for
# default compose filenames in the current directory.
#
# Arguments:
#   $@: The arguments passed to the main script.
# Returns:
#   string: The path to the found compose file. Exits if not found.
################################################################################
find_compose_file() {
    local args=("$@")
    local compose_file=""

    # Look for -f or --file arguments
    for i in "${!args[@]}"; do
        if [[ "${args[$i]}" == "-f" || "${args[$i]}" == "--file" ]]; then
            # Check if the next argument exists and is the filename
            if [[ -n "${args[$i+1]}" ]]; then
                compose_file="${args[$i+1]}"
                if [[ -f "$compose_file" ]]; then
                    echo "Info (find_compose_file): Using specified compose file: $compose_file" >&2
                    echo "$compose_file"
                    return 0
                else
                    echo "Error (find_compose_file): Specified compose file '$compose_file' not found." >&2
                    return 1
                fi
            fi
        fi
    done

    # If not specified, search for default files
    local default_files=(
        "compose.yaml"
        "compose.yml"
        "docker-compose.yaml"
        "docker-compose.yml"
    )

    for file in "${default_files[@]}"; do
        if [[ -f "$file" ]]; then
            echo "Info (find_compose_file): Found default compose file: $file" >&2
            echo "$file"
            return 0
        fi
    done

    echo "Error (find_compose_file): No compose file specified and no default file found." >&2
    echo "Info: Searched for ${default_files[*]}" >&2
    return 1
}


################################################################################
# Parses a Docker port specification string and extracts the host port.
# Appends valid, numeric host ports to the global array `host_ports_to_open_list`.
#
# Globals:
#   host_ports_to_open_list (modified): This array is appended with extracted
#                                       host port numbers.
# Arguments:
#   $1: port_spec (string) - The port specification string (e.g., "8080:80").
################################################################################
parse_docker_port_spec() {
    local port_spec_arg="$1"
    local host_port_candidate=""

    # Handles format like "8080:80/tcp" by removing the protocol part
    local cleaned_spec="${port_spec_arg%%/*}"
    # Handles format like "127.0.0.1:8080:80" or "8080:80"
    # shellcheck disable=SC2207
    IFS=':' read -r -a parts <<< "$cleaned_spec"

    if [[ ${#parts[@]} -ge 2 ]]; then
        # In "8080:80", host port is the first part.
        # In "127.0.0.1:8080:80", host port is the second part.
        host_port_candidate="${parts[-2]}"
    fi

    # Validate and add the port
    if [[ -n "$host_port_candidate" ]] && [[ "$host_port_candidate" =~ ^[0-9]+$ ]]; then
        if [ "$host_port_candidate" -ge 1 ] && [ "$host_port_candidate" -le 65535 ]; then
            host_ports_to_open_list+=("$host_port_candidate")
        else
            echo "Warning (parse_docker_port_spec): Extracted host port '$host_port_candidate' from '$port_spec_arg' is not a valid port number (1-65535)." >&2
        fi
    elif [[ -n "$port_spec_arg" ]]; then
        # Check if it's a case without an explicit host port (e.g., "-p 80")
        local is_just_container_port=false
        if [[ ${#parts[@]} -eq 1 && "${parts[0]}" =~ ^[0-9]+$ ]]; then
             is_just_container_port=true
        fi

        if ! $is_just_container_port; then
            echo "Warning (parse_docker_port_spec): Could not extract an explicit host port from '$port_spec_arg'. Docker will handle it." >&2
        fi
    fi
}


################################################################################
# Parses a Docker Compose file to extract all published host ports.
#
# Arguments:
#   $@: The arguments passed to the main script.
# Returns:
#   0 on success, 1 on failure.
################################################################################
handle_compose_ports() {
    local compose_file
    compose_file=$(find_compose_file "$@")
    if [[ $? -ne 0 ]]; then
        return 1
    fi

    # Using yq to extract port definitions from the compose file.
    # '.services[].ports[]' gets all items from all 'ports' lists under 'services'.
    # The '?' handles cases where a service might not have a 'ports' section.
    local port_specs
    port_specs=$(yq '.services[].ports[]?' "$compose_file")
    if [[ $? -ne 0 ]]; then
        echo "Error (handle_compose_ports): 'yq' failed to parse '$compose_file'." >&2
        return 1
    fi

    if [[ -z "$port_specs" ]]; then
        echo "Info (handle_compose_ports): No port definitions found in '$compose_file'." >&2
        return 0
    fi

    # Each port spec is on a new line, process them one by one.
    while IFS= read -r spec; do
        if [[ -n "$spec" ]]; then
            parse_docker_port_spec "$spec"
        fi
    done <<< "$port_specs"

    return 0
}

################################################################################
# Parses command-line arguments to find -p or --publish flags and extract ports.
#
# Arguments:
#   $@: The arguments passed to the main script.
# Returns:
#   0 (always)
################################################################################
handle_publish_args() {
    local original_docker_args=("$@")
    local i=0
    local num_args=${#original_docker_args[@]}

    while [[ $i -lt $num_args ]]; do
        local current_arg="${original_docker_args[$i]}"
        local port_spec_from_arg=""

        case "$current_arg" in
            -p|--publish)
                ((i++))
                if [[ $i -lt $num_args ]]; then
                    port_spec_from_arg="${original_docker_args[$i]}"
                else
                    echo "Warning: Docker command might fail: Missing value for '$current_arg' option." >&2
                fi
                ;;
            --publish=*)
                port_spec_from_arg="${current_arg#*=}"
                ;;
        esac

        if [[ -n "$port_spec_from_arg" ]]; then
            parse_docker_port_spec "$port_spec_from_arg"
        fi
        ((i++))
    done
    return 0
}


################################################################################
# Checks if a given port exists in the specified Kubernetes service.
# If the port does not exist, it adds the port to the service and applies
# the changes.
#
# Globals:
#   K8S_SERVICE_NAME, K8S_NAMESPACE, K8S_DEFAULT_PROTOCOL
# Arguments:
#   $1: port_number (int) - The port number to check and potentially add.
# Returns:
#   0 if the port was added successfully or already existed.
#   1 if an error occurred.
################################################################################
manage_service_port() {
    local port_number
    local port_name
    local service_json
    local existing_port_json
    local updated_service_json

    port_number="$1"

    # --- Input validation ---
    if ! [[ "$port_number" =~ ^[0-9]+$ ]] || [ "$port_number" -lt 1 ] || [ "$port_number" -gt 65535 ]; then
        echo "Error (manage_service_port): Invalid port number '$port_number'." >&2
        return 1
    fi

    # --- Retrieve service definition ---
    service_json=$(kubectl get service "$K8S_SERVICE_NAME" -n "$K8S_NAMESPACE" -o json)
    if [[ $? -ne 0 || -z "$service_json" ]]; then
        echo "Error (manage_service_port): Service '$K8S_SERVICE_NAME' not found in namespace '$K8S_NAMESPACE'." >&2
        return 1
    fi

    # --- Check if port already exists ---
    existing_port_json=$(echo "$service_json" | jq --argjson p "$port_number" --arg proto "$K8S_DEFAULT_PROTOCOL" \
        '.spec.ports[]? | select(.port == $p and (.protocol == $proto or .protocol == null and $proto == "TCP"))')

    if [[ -n "$existing_port_json" ]]; then
        echo "Info (manage_service_port): Port '$port_number' already exists on service '$K8S_SERVICE_NAME'." >&2
        return 0
    fi

    # --- Add the new port ---
    port_name="$(echo "$K8S_DEFAULT_PROTOCOL" | tr '[:upper:]' '[:lower:]')-${port_number}"

    updated_service_json=$(echo "$service_json" | jq \
        --argjson pn "$port_number" \
        --argjson tp "$port_number" \
        --arg proto "$K8S_DEFAULT_PROTOCOL" \
        --arg name "$port_name" \
        '.spec.ports = (.spec.ports // []) + [{"name": $name, "port": $pn, "targetPort": $pn, "protocol": $proto}]')

    if [[ $? -ne 0 || -z "$updated_service_json" ]]; then
        echo "Error (manage_service_port): Failed to add port '$port_number' to service JSON using jq." >&2
        return 1
    fi

    # Apply the updated service configuration
    echo "$updated_service_json" | kubectl apply -f -
    if [[ $? -ne 0 ]]; then
        echo "Error (manage_service_port): Failed to apply updated service configuration for '$K8S_SERVICE_NAME'." >&2
        return 1
    fi

    echo "Success (manage_service_port): Port '$port_number/$K8S_DEFAULT_PROTOCOL' (named '$port_name') added to service '$K8S_SERVICE_NAME'."
    return 0
}


################################################################################
# Main wrapper function that orchestrates port detection and management before
# executing the final Docker command.
#
# Arguments:
#   $@: All arguments passed to the script, intended for the Docker command.
################################################################################
main_wrapper() {
    # --- Dependency checks ---
    for cmd in kubectl jq docker yq; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "Error: Required command '$cmd' not found. Please install it." >&2
            return 1
        fi
    done

    # --- Port detection logic ---
    if [[ "$1" == "compose" ]]; then
        echo "Info: Docker Compose command detected. Parsing for ports..." >&2
        if ! handle_compose_ports "$@"; then
            echo "Error: Failed to process compose file. Aborting." >&2
            return 1
        fi
    else
        echo "Info: Non-compose command detected. Parsing for --publish flags..." >&2
        handle_publish_args "$@"
    fi

    # --- Port management logic ---
    if [[ ${#host_ports_to_open_list[@]} -gt 0 ]]; then
        local unique_ports_to_manage
        unique_ports_to_manage=$(echo "${host_ports_to_open_list[@]}" | tr ' ' '\n' | sort -un | tr '\n' ' ')

        echo "Info: Ports to manage on service '$K8S_SERVICE_NAME': $unique_ports_to_manage" >&2

        for port_to_manage in $unique_ports_to_manage; do
            if [[ -n "$port_to_manage" ]]; then
                if ! manage_service_port "$port_to_manage"; then
                    echo "Error: Failed to ensure port $port_to_manage is open on service '$K8S_SERVICE_NAME'." >&2
                    echo "Error: Aborting before executing Docker command due to port management failure." >&2
                    return 1
                fi
            fi
        done
    else
        echo "Info: No explicit host ports found to manage." >&2
    fi

    # --- Execute the original Docker command ---
    echo "Info: Executing Docker command..." >&2
    docker --context kube "$@"
    local docker_exit_code=$?

    if [[ $docker_exit_code -ne 0 ]]; then
        echo "Warning: Docker command exited with status $docker_exit_code." >&2
    fi
    return $docker_exit_code
}

# Entrypoint guard
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main_wrapper "$@"
fi