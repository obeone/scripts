#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utility script to ease launching a privileged debug container in Kubernetes."""

import argparse
import subprocess
import sys
import json
import uuid
import os
import atexit
import shutil
import logging
import coloredlogs
from typing import List, Optional, Dict, Any, Tuple

# --- Kubernetes Client Library Imports ---
try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    # Define ApiException for type hints if kubernetes library is not installed,
    # allowing the script to run for --completion generation or help.
    class ApiException(Exception):  # type: ignore
        '''Custom ApiException placeholder if kubernetes library is not installed.'''
        def __init__(self, status: int = 0, reason: str = ""):
            super().__init__(reason)
            self.status = status
            self.reason = reason
            self.body = None
            self.headers = None

# --- Configuration ---
DEFAULT_DEBUG_IMAGE = "harbor.obeone.cloud/public/netshoot:debian-podman"
# Map string levels to logging constants
LOG_LEVEL_MAP = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warn': logging.WARNING,
    'error': logging.ERROR,
}
SCRIPT_NAME = os.path.basename(__file__)

# --- Logger Setup (will be configured in main after parsing args) ---
logger = logging.getLogger()

# --- Kubernetes API Interaction ---
core_v1_api: Optional['client.CoreV1Api'] = None
k8s_client_initialized_ctx: Optional[str] = None

def init_k8s_client(context: Optional[str] = None, force_reload: bool = False) -> bool:
    '''
    Initializes or re-initializes the Kubernetes API client.

    This function loads the Kubernetes configuration for the specified context (or default)
    and initializes the CoreV1Api client. It handles cases where the Kubernetes
    library might not be available.

    Args:
        context (Optional[str]): The Kubernetes context to load. If None, the default context is used.
        force_reload (bool): If True, forces a reload of the client even if it was previously
                             initialized for the same context.

    Returns:
        bool: True if the client was successfully initialized, False otherwise.
    '''
    global core_v1_api, k8s_client_initialized_ctx
    if k8s_client_initialized_ctx is not None and k8s_client_initialized_ctx == context and not force_reload:
        return core_v1_api is not None

    if not KUBERNETES_AVAILABLE:
        # Log only if logger is configured (i.e., not during very early --completion check)
        if logger.handlers:
            logger.error("Kubernetes library is required but not installed.")
        else:
            # Fallback to print if logger is not yet set up (e.g. during arg parsing for completion)
            print("[ERROR] Kubernetes library is required but not installed.", file=sys.stderr)
        return False
    try:
        logger.debug(f"Loading K8s config (context: {context or 'default'})")
        config.load_kube_config(context=context)
        core_v1_api = client.CoreV1Api()
        k8s_client_initialized_ctx = context
        return True
    except (ConfigException, Exception) as e: # pylint: disable=broad-except
        logger.error(f"K8s client init failed (context: {context}): {e}")
        core_v1_api = None
        k8s_client_initialized_ctx = None
        # Exit only if running normally, not during completion list generation
        # or if the script is called to generate the completion script itself.
        if not any(arg.startswith('--_list') for arg in sys.argv) and '--completion' not in sys.argv:
            sys.exit(1)
        return False

# --- K8s Data Fetching Functions (for completion and main logic) ---

def get_contexts() -> List[str]:
    '''
    Retrieves a list of available Kubernetes contexts from the kubeconfig file.

    Returns:
        List[str]: A sorted list of context names. Returns an empty list if the
                   Kubernetes library is not available or if an error occurs during
                   context listing.
    '''
    if not KUBERNETES_AVAILABLE:
        return []
    try:
        contexts_list, _ = config.list_kube_config_contexts()
        return sorted([ctx['name'] for ctx in contexts_list])
    except (ConfigException, Exception) as e: # pylint: disable=broad-except
        logger.error(f"Failed to list kubeconfig contexts: {e}")
        return []

def get_namespaces(context_for_api: Optional[str] = None) -> List[str]:
    '''
    Retrieves a list of namespaces for a given Kubernetes context.

    Initializes the Kubernetes API client for the specified context if not already
    initialized or if the context differs.

    Args:
        context_for_api (Optional[str]): The Kubernetes context to use for the API call.
                                         If None, the client's current or default context is used.

    Returns:
        List[str]: A sorted list of namespace names. Returns an empty list if an error occurs
                   or the API client cannot be initialized.
    '''
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            namespaces = core_v1_api.list_namespace()
            return sorted([ns.metadata.name for ns in namespaces.items if ns.metadata and ns.metadata.name])
        except ApiException as e:
            logger.error(f"API error listing namespaces: {e.status} {e.reason}")
    return []

def get_pods(namespace: str, context_for_api: Optional[str] = None) -> List[str]:
    '''
    Retrieves a list of pod names in a specific namespace and context.

    Args:
        namespace (str): The namespace from which to list pods.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        List[str]: A sorted list of pod names. Returns an empty list on error.
    '''
    if namespace and init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pods = core_v1_api.list_namespaced_pod(namespace=namespace)
            return sorted([pod.metadata.name for pod in pods.items if pod.metadata and pod.metadata.name])
        except ApiException as e:
            logger.error(f"API error listing pods in ns {namespace}: {e.status} {e.reason}")
    return []

def get_containers(namespace: str, pod_name: str, context_for_api: Optional[str] = None) -> List[str]:
    '''
    Retrieves a list of container names for a specific pod.

    Args:
        namespace (str): The namespace of the pod.
        pod_name (str): The name of the pod.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        List[str]: A list of container names. Returns an empty list on error or if not found.
    '''
    if namespace and pod_name and init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.spec and pod.spec.containers:
                return [c.name for c in pod.spec.containers]
        except ApiException as e:
            if e.status != 404:  # Log unless it's a simple not found
                logger.error(
                    "API error reading pod %s to get containers: %s %s",
                    pod_name,
                    e.status,
                    e.reason,
                )
    return []

# --- Completion Script Generation ---
# Templates are kept as is for brevity in this response, assume they are correct.
BASH_COMPLETION_TEMPLATE = """\
#!/usr/bin/env bash
# Bash completion script for {script_name}
_ks_py_completions() {{ local cur prev words cword split=false; _get_comp_words_by_ref -n : cur prev words cword; case "$prev" in -C|--context) COMPREPLY=($(compgen -W '$({script_name} --_list-contexts)' -- "$cur")); return 0 ;; -n|--namespace) local kcontext=$(_get_kcontext_from_cmdline); COMPREPLY=($(compgen -W '$({script_name} $kcontext --_list-namespaces)' -- "$cur")); return 0 ;; -p|--pod) local kcontext=$(_get_kcontext_from_cmdline); local knamespace=$(_get_knamespace_from_cmdline); if [[ -n "$knamespace" ]]; then COMPREPLY=($(compgen -W '$({script_name} $kcontext --namespace "$knamespace" --_list-pods)' -- "$cur")); fi; return 0 ;; -c|--container) local kcontext=$(_get_kcontext_from_cmdline); local knamespace=$(_get_knamespace_from_cmdline); local kpod=$(_get_kpod_from_cmdline); if [[ -n "$knamespace" && -n "$kpod" ]]; then COMPREPLY=($(compgen -W '$({script_name} $kcontext --namespace "$knamespace" --pod "$kpod" --_list-containers)' -- "$cur")); fi; return 0 ;; -i|--image) _filedir; return 0 ;; -l|--log-level) COMPREPLY=($(compgen -W 'debug info warn error' -- "$cur")); return 0 ;; esac; if [[ "$cur" == -* ]]; then COMPREPLY=($(compgen -W '-C --context -n --namespace -p --pod -c --container -i --image --dry-run -l --log-level -h --help' -- "$cur")); return 0; fi }}
_get_kcontext_from_cmdline() {{ local i=1; while [[ $i -lt $cword ]]; do if [[ ${{words[i]}} == "-C" || ${{words[i]}} == "--context" ]]; then local j=$((i + 1)); if [[ $j -lt $cword ]]; then echo "--context ${{words[j]}}"; return; fi; fi; i=$((i + 1)); done; echo ""; }}
_get_knamespace_from_cmdline() {{ local i=1; while [[ $i -lt $cword ]]; do if [[ ${{words[i]}} == "-n" || ${{words[i]}} == "--namespace" ]]; then local j=$((i + 1)); if [[ $j -lt $cword ]]; then echo "${{words[j]}}"; return; fi; fi; i=$((i + 1)); done; echo ""; }}
_get_kpod_from_cmdline() {{ local i=1; while [[ $i -lt $cword ]]; do if [[ ${{words[i]}} == "-p" || ${{words[i]}} == "--pod" ]]; then local j=$((i + 1)); if [[ $j -lt $cword ]]; then echo "${{words[j]}}"; return; fi; fi; i=$((i + 1)); done; echo ""; }}
complete -F _ks_py_completions {script_name}
"""
ZSH_COMPLETION_TEMPLATE = r"""#compdef {script_name}
# Zsh completion script for {script_name}
_ks_py_completions() {{ local context state state_descr line=() ret=1; local -a k_contexts k_namespaces k_pods k_containers log_levels; log_levels=( 'debug:Log level for detailed debugging' 'info:Log level for informational messages' 'warn:Log level for warnings (default)' 'error:Log level for errors only' ); local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p'); local knamespace_val=$(echo $words | sed -n -E 's/.* (--namespace|-n) ([^ ]*).*/\2/p'); local kpod_val=$(echo $words | sed -n -E 's/.* (--pod|-p) ([^ ]*).*/\2/p'); _arguments -C -s -S '(- *)'{{-C,--context=}}'[Specify kube context]:Kubernetes context:_ks_py_get_contexts' '(- *)'{{-n,--namespace=}}'[Specify namespace]:Kubernetes namespace:_ks_py_get_namespaces' '(- *)'{{-p,--pod=}}'[Specify pod name]:Pod name:_ks_py_get_pods' '(- *)'{{-c,--container=}}'[Specify container name]:Container name:_ks_py_get_containers' '(- *)'{{-i,--image=}}'[Specify debug image]:Debug container image:_files' '--dry-run[Only print the command without running it]' '(- *)'{{-l,--log-level=}}'[Set log level]:Log level: _values "Log Level" $log_levels' '(-h --help)'{{-h,--help}}'[Show help message]' '*::Args: ' && ret=0; return $ret }}
_ks_py_get_contexts() {{ compadd $( {script_name} --_list-contexts ) }}
_ks_py_get_namespaces() {{ local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p'); compadd $( {script_name} $kcontext_arg --_list-namespaces ) }}
_ks_py_get_pods() {{ local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p'); local knamespace_val=$(echo $words | sed -n -E 's/.* (--namespace|-n) ([^ ]*).*/\2/p'); if [[ -n "$knamespace_val" ]]; then compadd $( {script_name} $kcontext_arg --namespace "$knamespace_val" --_list-pods ); fi }}
_ks_py_get_containers() {{ local kcontext_arg=$(echo $words | sed -n -E 's/.* (--context|-C) ([^ ]*).*/\1 \2/p'); local knamespace_val=$(echo $words | sed -n -E 's/.* (--namespace|-n) ([^ ]*).*/\2/p'); local kpod_val=$(echo $words | sed -n -E 's/.* (--pod|-p) ([^ ]*).*/\2/p'); if [[ -n "$knamespace_val" && -n "$kpod_val" ]]; then compadd $( {script_name} $kcontext_arg --namespace "$knamespace_val" --pod "$kpod_val" --_list-containers ); fi }}
_ks_py_completions "$@"
"""
FISH_COMPLETION_TEMPLATE = """\
# Fish completion script for {script_name}
function __ks_py_get_contexts; {script_name} --_list-contexts; end
function __ks_py_get_namespaces; set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' ''); set -l context_option; if test -n "$kcontext_arg"; set context_option --context $kcontext_arg; end; {script_name} $context_option --_list-namespaces; end
function __ks_py_get_pods; set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' ''); set -l knamespace_arg (commandline -opc | string match -r -- '(--namespace=|-n)([^ ]+)' | string replace -r -- '(--namespace=|-n)' ''); set -l context_option; set -l namespace_option; if test -n "$kcontext_arg"; set context_option --context $kcontext_arg; end; if test -n "$knamespace_arg"; set namespace_option --namespace $knamespace_arg; end; if test -n "$namespace_option"; {script_name} $context_option $namespace_option --_list-pods; end; end
function __ks_py_get_containers; set -l kcontext_arg (commandline -opc | string match -r -- '(--context=|-C)([^ ]+)' | string replace -r -- '(--context=|-C)' ''); set -l knamespace_arg (commandline -opc | string match -r -- '(--namespace=|-n)([^ ]+)' | string replace -r -- '(--namespace=|-n)' ''); set -l kpod_arg (commandline -opc | string match -r -- '(--pod=|-p)([^ ]+)' | string replace -r -- '(--pod=|-p)' ''); set -l context_option; set -l namespace_option; set -l pod_option; if test -n "$kcontext_arg"; set context_option --context $kcontext_arg; end; if test -n "$knamespace_arg"; set namespace_option --namespace $knamespace_arg; end; if test -n "$kpod_arg"; set pod_option --pod $kpod_arg; end; if test -n "$namespace_option" && test -n "$pod_option"; {script_name} $context_option $namespace_option $pod_option --_list-containers; end; end
complete -c {script_name} -n "__fish_use_subcommand" -l context -s C -d "Specify kube context" -a "(__ks_py_get_contexts)"
complete -c {script_name} -n "__fish_use_subcommand" -l namespace -s n -d "Specify namespace" -a "(__ks_py_get_namespaces)"
complete -c {script_name} -n "__fish_use_subcommand" -l pod -s p -d "Specify pod name" -a "(__ks_py_get_pods)"
complete -c {script_name} -n "__fish_use_subcommand" -l container -s c -d "Specify container name" -a "(__ks_py_get_containers)"
complete -c {script_name} -n "__fish_use_subcommand" -l image -s i -d "Specify debug image" -r -F
complete -c {script_name} -n "__fish_use_subcommand" -l dry-run -d "Only print the command without running it"
complete -c {script_name} -n "__fish_use_subcommand" -l log-level -s l -d "Set log level" -a "debug info warn error"
complete -c {script_name} -n "__fish_use_subcommand" -l help -s h -d "Show help message"
"""

def print_completion_script(shell: str):
    '''
    Prints the completion script for the specified shell.

    Args:
        shell (str): The target shell ('bash', 'zsh', or 'fish').

    Raises:
        SystemExit: If the shell is unsupported.
    '''
    script_content = ""
    if shell == 'bash':
        script_content = BASH_COMPLETION_TEMPLATE.format(script_name=SCRIPT_NAME)
    elif shell == 'zsh':
        script_content = ZSH_COMPLETION_TEMPLATE.format(script_name=SCRIPT_NAME)
    elif shell == 'fish':
        script_content = FISH_COMPLETION_TEMPLATE.format(script_name=SCRIPT_NAME)
    else:
        # Logger might not be configured at this point if called very early.
        print(f"[ERROR] Unsupported shell for completion: {shell}. Choose bash, zsh, or fish.", file=sys.stderr)
        sys.exit(1)
    print(script_content)

# --- Functions for normal execution flow ---

def handle_api_exception_norm(e: ApiException, operation_desc: str) -> None:
    '''
    Handles ApiException during normal script execution by logging and exiting.

    Args:
        e (ApiException): The caught Kubernetes ApiException.
        operation_desc (str): A description of the K8s operation that failed.

    Raises:
        SystemExit: Always exits the script with status 1.
    '''
    logger.error(f"API error during '{operation_desc}': Status {e.status}, Reason: {e.reason}")
    if e.body:
        try:
            error_body = json.loads(e.body)
            logger.error(f"Details: {error_body.get('message', e.body)}")
        except json.JSONDecodeError:
            logger.error(f"Details (raw): {e.body}")
    if e.status == 403:
        logger.error("Suggestion: Check RBAC permissions for the K8s user/service account.")
    elif e.status == 404:
        logger.error("Suggestion: Check if the targeted Kubernetes resource exists and names are correct.")
    sys.exit(1)

def get_pods_with_node_display(namespace: str, context_for_api: Optional[str] = None) -> List[str]:
    '''
    Retrieves a list of pods in a namespace, formatted with their node names.

    Args:
        namespace (str): The namespace to query.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        List[str]: A list of strings, each "pod_name node_name". Empty if error.
    '''
    pods_info: List[str] = []
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pods = core_v1_api.list_namespaced_pod(namespace=namespace)
            for pod in pods.items:
                if (
                    pod.metadata
                    and pod.metadata.name
                    and pod.spec
                    and pod.spec.node_name
                ):
                    pods_info.append(f"{pod.metadata.name} {pod.spec.node_name}")
                else:
                    logger.debug(
                        "Skipping pod with incomplete data: %s",
                        getattr(pod.metadata, "name", "N/A"),
                    )
        except ApiException as e:
            handle_api_exception_norm(e, f"list pods in namespace {namespace}")
    return pods_info  # Will be empty if handle_api_exception_norm exited

def get_pod_metadata_display(namespace: str, pod_name: str, container_name: str, context_for_api: Optional[str] = None) -> Optional[Dict[str, Any]]:
    '''
    Retrieves detailed metadata for a specific container within a pod.

    Args:
        namespace (str): The namespace of the pod.
        pod_name (str): The name of the pod.
        container_name (str): The name of the container.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        Optional[Dict[str, Any]]: A dictionary with pod and container metadata, or None on error.
    '''
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            selected_container_obj = next((c for c in (pod.spec.containers or []) if c.name == container_name), None)

            if not selected_container_obj:
                logger.warning(f"Container '{container_name}' not found in pod '{pod_name}'.")
                return None

            resources_dict = {}
            if selected_container_obj.resources:
                if selected_container_obj.resources.limits:
                    resources_dict['limits'] = selected_container_obj.resources.limits
                if selected_container_obj.resources.requests:
                    resources_dict['requests'] = selected_container_obj.resources.requests

            metadata = {
                "pod": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "node": pod.spec.node_name,
                "container_name": selected_container_obj.name,
                "image": selected_container_obj.image,
                "resources": client.ApiClient().sanitize_for_serialization(resources_dict) or {},
            }
            return metadata
        except ApiException as e:
            handle_api_exception_norm(e, f"read pod {pod_name} in namespace {namespace}")
            return None # Should not be reached if handle_api_exception_norm exits
    return None

def check_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    '''
    Checks if a namespace has the 'pod-security.kubernetes.io/enforce: privileged' label.

    Args:
        namespace (str): The namespace to check.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        bool: True if the label is present and set to 'privileged', False otherwise.

    Raises:
        SystemExit: If namespace is not found or other API error handled by handle_api_exception_norm.
    '''
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            ns_obj = core_v1_api.read_namespace(name=namespace)
            if ns_obj.metadata and ns_obj.metadata.labels:
                label_value = ns_obj.metadata.labels.get("pod-security.kubernetes.io/enforce")
                return label_value == "privileged"
        except ApiException as e:
            if e.status == 404:
                logger.error(f"Namespace '{namespace}' not found.")
                sys.exit(1)
            else:
                handle_api_exception_norm(e, f"read namespace {namespace}")
    return False # Should not be reached if handle_api_exception_norm exits or 404 exit

def apply_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    '''
    Applies the 'pod-security.kubernetes.io/enforce: privileged' label to a namespace.

    Args:
        namespace (str): The namespace to label.
        context_for_api (Optional[str]): The Kubernetes context to use.

    Returns:
        bool: True if successfully labeled, False otherwise.
              (Note: Exits on API error via handle_api_exception_norm).
    '''
    if init_k8s_client(context=context_for_api) and core_v1_api:
        logger.warning(f"Applying 'pod-security.kubernetes.io/enforce: privileged' label to namespace '{namespace}'.")
        patch_body = {"metadata": {"labels": {"pod-security.kubernetes.io/enforce": "privileged"}}}
        try:
            core_v1_api.patch_namespace(name=namespace, body=patch_body)
            logger.info(f"Successfully applied privileged label to namespace '{namespace}'.")
            return True
        except ApiException as e:
            handle_api_exception_norm(e, f"patch namespace {namespace} to apply label")
    return False # Should not be reached

def remove_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> None:
    '''
    Removes the 'pod-security.kubernetes.io/enforce' label from a namespace.

    Uses a JSON Patch operation to remove the label. Handles cases where the
    label or namespace might not exist.

    Args:
        namespace (str): The namespace from which to remove the label.
        context_for_api (Optional[str]): The Kubernetes context to use.
    '''
    if init_k8s_client(context=context_for_api) and core_v1_api:
        logger.info(f"Attempting to remove 'pod-security.kubernetes.io/enforce' label from namespace '{namespace}'.")
        # The label key "pod-security.kubernetes.io/enforce" contains a '/'.
        # In JSON Patch path, '/' is represented as '~1'.
        label_key_for_patch = "pod-security.kubernetes.io~1enforce"
        patch_body = [{"op": "remove", "path": f"/metadata/labels/{label_key_for_patch}"}]

        try:
            core_v1_api.patch_namespace(name=namespace, body=patch_body)
            logger.info(
                "Label 'pod-security.kubernetes.io/enforce' removed from namespace '%s' if present.",
                namespace,
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Namespace '{namespace}' not found during label removal attempt.")
            elif e.status in [400, 422]:  # Bad Request or Unprocessable Entity
                error_msg = f"API error ({e.status}) during label removal for '{namespace}'"
                try:
                    error_details = json.loads(e.body)
                    # Check for specific Kubernetes error messages related to patching non-existent paths
                    msg_lower = str(error_details.get("message", "")).lower()
                    if "remove operation does not apply" in msg_lower or \
                       "path does not exist" in msg_lower or \
                       "not found" in msg_lower or \
                       "testPath path does not exist" in msg_lower: # More specific check for patch
                        logger.debug(f"Label '{label_key_for_patch.replace('~1','/')}' likely already removed or never existed on namespace '{namespace}'. Details: {msg_lower}")
                    else:
                        logger.warning(f"{error_msg}. Details: {error_details.get('message', e.body)}")
                except json.JSONDecodeError:
                    logger.warning(f"{error_msg}. Raw body: {e.body}")
            else:
                # General API error
                logger.warning(f"API error during label removal for namespace '{namespace}': {e.status} {e.reason}")
                if e.body:
                    logger.warning(f"Error body: {e.body}")
    else:
        logger.warning(f"Cannot remove label for '{namespace}': K8s client unavailable or not initialized for context.")


# --- External Command Execution, FZF, Cleanup ---
def run_command(command: List[str], check: bool = True, capture_output: bool = True, text: bool = True, input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    '''
    Executes an external command using subprocess.

    Args:
        command (List[str]): The command and its arguments as a list of strings.
        check (bool): If True, raises CalledProcessError if the command returns a non-zero exit code.
        capture_output (bool): If True, stdout and stderr will be captured.
        text (bool): If True, stdout and stderr will be decoded as text.
        input_data (Optional[str]): Data to be sent to the command's stdin.

    Returns:
        subprocess.CompletedProcess: An object containing information about the completed process.

    Raises:
        SystemExit: If the command is not found, fails (and check=True), or an unexpected error occurs.
    '''
    logger.debug(f"Running external command: {' '.join(command)}")
    try:
        result = subprocess.run(
            command, check=check, capture_output=capture_output, text=text, input=input_data
        )
        if capture_output and result.stderr and result.stderr.strip() and logger.isEnabledFor(logging.DEBUG):
            logger.debug("External command stderr: %s", result.stderr.strip())
        if capture_output and result.stdout and logger.isEnabledFor(logging.DEBUG):
            logger.debug("External command stdout: %s", result.stdout.strip())
        return result
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        stderr_info = f" Stderr: {e.stderr.strip()}" if e.stderr and capture_output else ""
        logger.error(f"External command failed: {' '.join(command)} (Exit code: {e.returncode}).{stderr_info}")
        sys.exit(1)
    except Exception as e: # pylint: disable=broad-except
        logger.error(f"Unexpected error running external command {' '.join(command)}: {e}")
        sys.exit(1)

def fzf_select(items: List[str], prompt: str) -> Optional[str]:
    '''
    Uses fzf to allow the user to select an item from a list.

    Args:
        items (List[str]): A list of strings to choose from.
        prompt (str): The prompt to display in fzf.

    Returns:
        Optional[str]: The selected item, or None if no item was selected or fzf was cancelled.

    Raises:
        SystemExit: If 'fzf' command is not found or if fzf exits due to an error
                    handled by run_command (e.g. fzf returns specific error codes not 130).
                    fzf exit code 130 (Ctrl+C) is handled as no selection.
    '''
    if not items:
        return None
    if not shutil.which("fzf"):
        logger.error("'fzf' command not found. Please install fzf to use this feature.")
        sys.exit(1)
    try:
        fzf_cmd = ["fzf", "--height", "20%", "--prompt", prompt]
        input_str = "\n".join(items)
        # run_command will sys.exit on errors other than non-zero if check=True.
        # We expect fzf to return 0 on selection, 1 on no match, 130 on ESC/Ctrl+C.
        # We want to treat 1 and 130 as "no selection" and not exit.
        process = subprocess.run(fzf_cmd, input=input_str, capture_output=True, text=True, check=False)
        if process.returncode == 0: # Selected
            return process.stdout.strip()
        if process.returncode == 130: # User aborted (ESC, Ctrl+C)
            logger.info("Selection cancelled by user (fzf exit code 130).")
            return None
        if process.returncode == 1: # No match / immediate exit
            logger.info("No item selected or matched in fzf (fzf exit code 1).")
            return None
        # For other fzf error codes, log and treat as critical error
        logger.error(f"fzf exited with unexpected code {process.returncode}. Stderr: {process.stderr.strip()}")
        sys.exit(1) # Exit for unexpected fzf errors
    except SystemExit: # Re-raise SystemExit if run_command itself decided to exit (e.g. fzf not found)
        raise
    except Exception as e: # pylint: disable=broad-except
        logger.error(f"Unexpected error during fzf execution: {e}")
        sys.exit(1) # Exit for other unexpected errors

cleanup_tasks: List[Tuple[Any, Tuple, Dict]] = []
def register_cleanup(func, *args, **kwargs) -> None:
    '''
    Registers a function to be called at script exit.

    Args:
        func (Callable): The function to call.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.
    '''
    cleanup_tasks.append((func, args, kwargs))

def run_cleanup() -> None:
    '''
    Runs all registered cleanup tasks in reverse order of registration.
    '''
    logger.debug("Running cleanup tasks...")
    for func, args, kwargs in reversed(cleanup_tasks):
        try:
            func(*args, **kwargs)
        except Exception as e: # pylint: disable=broad-except
            logger.warning(f"Error during cleanup task {getattr(func, '__name__', 'unknown_function')}: {e}")
atexit.register(run_cleanup)


# --- Main Execution Logic ---
def main():
    '''
    Main function to parse arguments and orchestrate the Kubernetes debug process.
    '''
    parser = argparse.ArgumentParser(
        description="Kubernetes Debug Helper Script. Helps in launching a debug container targeting a specific application container within a pod.",
        epilog=f"Example: {SCRIPT_NAME} -n my-namespace -p my-app-pod-xxxx -c my-app-container",
        add_help=False # Custom help argument added below
    )
    # Group for K8s targeting arguments
    k8s_group = parser.add_argument_group('Kubernetes Target Options')
    k8s_group.add_argument("-C", "--context", help="Specify Kubernetes context to use")
    k8s_group.add_argument("-n", "--namespace", help="Specify namespace (interactive if not provided)")
    k8s_group.add_argument("-p", "--pod", help="Specify pod name (interactive if not provided)")
    k8s_group.add_argument("-c", "--container", help="Specify container name (interactive if not provided, or auto if single)")

    # Group for debug session options
    debug_group = parser.add_argument_group('Debug Session Options')
    debug_group.add_argument("-i", "--image", default=DEFAULT_DEBUG_IMAGE,
                             help=f"Debug container image to use (default: {DEFAULT_DEBUG_IMAGE})")
    debug_group.add_argument("--dry-run", action="store_true",
                             help="Print the kubectl debug command that would be run, without executing it")

    # Group for script behavior options
    behavior_group = parser.add_argument_group('Script Behavior Options')
    behavior_group.add_argument("-l", "--log-level", choices=LOG_LEVEL_MAP.keys(), default="warn",
                                help="Set log level (default: warn)")
    behavior_group.add_argument("-h", "--help", action='help', default=argparse.SUPPRESS,
                                help="Show this help message and exit")

    # Suppressed arguments for completion logic
    parser.add_argument('--completion', choices=['bash', 'zsh', 'fish'], help=argparse.SUPPRESS)
    parser.add_argument('--_list-contexts', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--_list-namespaces', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--_list-pods', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--_list-containers', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()

    # --- Setup Logging ---
    log_level_name = args.log_level
    log_level_const = LOG_LEVEL_MAP.get(log_level_name, logging.WARNING)
    coloredlogs.install(
        level=log_level_const,
        logger=logger,
        fmt='[%(levelname)s] %(message)s',
        level_styles=coloredlogs.DEFAULT_LEVEL_STYLES,
        field_styles=coloredlogs.DEFAULT_FIELD_STYLES
    )
    logger.debug(f"Log level set to {log_level_name.upper()}")
    if not KUBERNETES_AVAILABLE and not args.completion:  # Don't log K8s missing if only generating completion script.
        logger.warning(
            "Python Kubernetes client library not found. Functionality will be limited."
        )
        # No sys.exit here, allow completion or help to proceed if possible.

    # --- Handle Meta Arguments (like completion list generation) ---
    # These require K8s lib, so check again if it wasn't available.
    if any([args._list_contexts, args._list_namespaces, args._list_pods, args._list_containers]):
        if not KUBERNETES_AVAILABLE:
            logger.error("Cannot generate dynamic completions: Kubernetes library not installed.")
            sys.exit(1)

    cb_context_arg = args.context # Context to use for completion callbacks
    if args._list_contexts:
        print('\n'.join(get_contexts())); sys.exit(0)
    if args._list_namespaces:
        print('\n'.join(get_namespaces(context_for_api=cb_context_arg))); sys.exit(0)
    if args._list_pods:
        if not args.namespace:
            # For completion, if namespace not given with --_list-pods, it's an issue with completer script.
            # or user trying to invoke it manually without -n.
            logger.debug("Namespace required for pod listing in completion mode.")
            sys.exit(1) # Exit, as completer expects output or nothing.
        print('\n'.join(get_pods(args.namespace, context_for_api=cb_context_arg))); sys.exit(0)
    if args._list_containers:
        if not args.namespace or not args.pod:
            logger.debug("Namespace and Pod required for container listing in completion mode.")
            sys.exit(1)
        print('\n'.join(get_containers(args.namespace, args.pod, context_for_api=cb_context_arg))); sys.exit(0)
    # --- End Handle Meta Arguments ---


    # --- Normal Execution Prerequisites ---
    if not KUBERNETES_AVAILABLE: # Critical for normal execution
        logger.error("Fatal: Python Kubernetes client library is required but not installed. Please install 'kubernetes'.")
        sys.exit(1)
    if not shutil.which("kubectl"):
        logger.error("Fatal: 'kubectl' command-line tool is required but not found in PATH.")
        sys.exit(1)
    if not shutil.which("fzf"):
        logger.error("Fatal: 'fzf' command-line tool is required for interactive selections but not found in PATH.")
        sys.exit(1)

    # Initialize K8s client for normal run. init_k8s_client handles errors and exits.
    if not init_k8s_client(context=args.context):
        # init_k8s_client already logged the error and exited if it failed critically.
        # This check is more of a safeguard or for linters.
        sys.exit(1) # Should be unreachable if init_k8s_client exits
    logger.debug("K8s client initialized for main execution.")

    context_arg = args.context # Use args.context which might be None
    namespace = args.namespace
    pod_name = args.pod
    container_name = args.container
    debug_image = args.image
    dry_run = args.dry_run

    # --- Interactive Selection using FZF ---
    try:
        if not namespace:
            namespaces_list = get_namespaces(context_for_api=context_arg)
            if not namespaces_list: logger.error("No namespaces found or accessible."); sys.exit(1)
            selected_ns = fzf_select(namespaces_list, "Select Namespace > ")
            if not selected_ns: logger.error("No namespace selected. Aborting."); sys.exit(1)
            namespace = selected_ns
        logger.info(f"Using namespace: {namespace}")

        if not pod_name:
            pods_with_nodes = get_pods_with_node_display(namespace, context_for_api=context_arg)
            if not pods_with_nodes: logger.error(f"No pods found in namespace '{namespace}'."); sys.exit(1)
            selected_pod_line = fzf_select(pods_with_nodes, f"Select Pod in '{namespace}' > ")
            if not selected_pod_line: logger.error("No pod selected. Aborting."); sys.exit(1)
            pod_name = selected_pod_line.split()[0] # Pod name is the first part
        logger.info(f"Using pod: {pod_name}")

        if not container_name:
            containers_list = get_containers(namespace, pod_name, context_for_api=context_arg)
            if not containers_list: logger.error(f"No containers found in pod '{pod_name}'."); sys.exit(1)
            if len(containers_list) == 1:
                container_name = containers_list[0]
                logger.info(f"Auto-selected only container: {container_name}")
            else:
                selected_container = fzf_select(containers_list, f"Select Container in '{pod_name}' > ")
                if not selected_container: logger.error("No container selected. Aborting."); sys.exit(1)
                container_name = selected_container
        logger.info(f"Using container: {container_name}")

        # --- Display Metadata ---
        metadata = get_pod_metadata_display(namespace, pod_name, container_name, context_for_api=context_arg)
        if metadata:
            logger.info("Selected Target Metadata:")
            # Use print for formatted multiline output, not logger
            print(f"  Context:     {k8s_client_initialized_ctx or 'current (default)'}")
            print(f"  Pod:         {metadata['pod']}")
            print(f"  Namespace:   {metadata['namespace']}")
            print(f"  Node:        {metadata['node']}")
            print(f"  Container:   {metadata['container_name']}")
            print(f"  Image:       {metadata['image']}")
            resources_str = json.dumps(metadata.get('resources',{}), indent=4).replace('\n', '\n               ')
            print(f"  Resources:   {resources_str if metadata.get('resources') else 'Not set'}")
        else:
            # get_pod_metadata_display would have exited via handle_api_exception_norm on API error
            logger.error(f"Failed to retrieve metadata for {namespace}/{pod_name}/{container_name}. This might indicate the container was not found post-selection.")
            sys.exit(1)

        # --- Namespace Labeling for Privileged Pods ---
        # This section is security sensitive.
        # The 'sysadmin' profile for `kubectl debug` often requires the namespace
        # to allow privileged pods if Pod Security Admission is active.

        # Simple check, could be more sophisticated by checking K8s version and PSA config
        if not check_namespace_label(namespace, context_for_api=context_arg):
            logger.warning(f"Namespace '{namespace}' does not have the 'pod-security.kubernetes.io/enforce: privileged' label.")
            logger.info("This label might be required for 'kubectl debug --profile=sysadmin' to work correctly with Pod Security Admission.")
            # Here, one might add a user confirmation step if desired.
            if apply_namespace_label(namespace, context_for_api=context_arg):
                # Register cleanup to remove the label ONLY if this script set it.
                register_cleanup(remove_namespace_label, namespace, context_for_api=context_arg)
            else:
                # apply_namespace_label would have exited on hard error.
                # If it returned False, it implies a non-critical failure or already handled.
                logger.error("Failed to apply privileged label to namespace. Debug session may fail.")
        else:
            logger.info(f"Namespace '{namespace}' already has the required privileged label or equivalent.")

        # --- Construct and Run Final Kubectl Debug Command ---
        # Use a unique name for the debug container to avoid collisions.
        debug_session_id = str(uuid.uuid4())[:8]
        debug_container_name = f"debug-{container_name}-{debug_session_id}"

        kubectl_cmd_list = ["kubectl"]
        if context_arg: # Add context if specified
            kubectl_cmd_list.extend(["--context", context_arg])
        kubectl_cmd_list.extend([
            "debug", pod_name,
            "--namespace", namespace,
            "--target", container_name, # Target the specific container process namespace
            "--image", debug_image,
            "--image-pull-policy=Always", # Ensure latest debug image
            "-c", debug_container_name, # Name for the new debug container
            "--profile=sysadmin",       # Requests privileged, host namespaces, etc.
            "--share-processes",        # Share PID namespace with the target container
            "-ti",                      # Allocate TTY and take stdin
            # Add any necessary overrides if not using --profile=sysadmin or needing specifics
            # e.g. "--override-pod-spec='{\"securityContext\": { ... }}'"
        ])

        final_command_str = ' '.join(kubectl_cmd_list)

        if dry_run:
            logger.info(f"[DRY RUN] Would execute: {final_command_str}")
        else:
            logger.info(f"Attempting to start debug session on '{namespace}/{pod_name}/{container_name}'...")
            logger.info(f"Executing: {final_command_str}")
            # run_command will exit on error
            run_command(
                kubectl_cmd_list,
                check=True,
                capture_output=False,
                text=False,
            )  # text=False for direct TTY
            logger.info("Debug session for '%s' finished.", debug_container_name)

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user (KeyboardInterrupt).")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except SystemExit as e:
        # Log SystemExit if it's not 0 (success) or 130 (user interrupt)
        if e.code not in [0, 1, 130]:  # fzf no selection often returns 1
            logger.debug("Exiting script with code %s due to SystemExit.", e.code)
        raise  # Re-raise to exit
    except Exception as e: # pylint: disable=broad-except
        logger.error(f"An unexpected error occurred in the main execution block: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # run_cleanup() is registered with atexit, so it will run automatically.
        # However, explicit call here could be an option if atexit was problematic.
        logger.debug("Main execution block finished or exited.")


if __name__ == "__main__":
    # Pre-check for --completion argument before full parsing or heavy imports.
    # This allows `script_name --completion bash` to be very fast.
    # Note: This simple check does not setup logging yet.
    if '--completion' in sys.argv:
        try:
            idx = sys.argv.index('--completion')
            if idx + 1 < len(sys.argv):
                shell_type = sys.argv[idx + 1]
                if shell_type in ['bash', 'zsh', 'fish']:
                    print_completion_script(shell_type)
                    sys.exit(0)
                else:
                    print(
                        f"[ERROR] Unsupported shell for completion: {shell_type}. Choose bash, zsh, or fish.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            else:
                print(
                    "[ERROR] Missing shell type (bash, zsh, or fish) after --completion.",
                    file=sys.stderr,
                )
                sys.exit(1)
        except ValueError:
            # Should not happen if '--completion' is in sys.argv
            pass # Let main argument parsing handle it if something is malformed

    main()
