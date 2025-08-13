#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A command-line utility to quickly launch a privileged debug container
targeting a pod in a Kubernetes cluster.

This tool simplifies the process of debugging applications running in Kubernetes
by providing an interactive way to select the target pod and container,
and then automatically launching a debug session. It handles namespace
security label management and offers various customization options.
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import uuid
import coloredlogs
from typing import Optional, List, Dict, Any

from .completion import print_completion_script
from .helpers import (
    run_command,
    fzf_select,
    register_cleanup,
    run_cleanup,
    check_command_availability,
)
from .k8s import (
    ApiException,
    KUBERNETES_AVAILABLE,
    apply_namespace_label,
    check_namespace_label,
    get_contexts,
    get_namespaces,
    get_pods,
    get_containers,
    get_pod_metadata_display,
    init_k8s_client,
    remove_namespace_label,
)

# Initialize logger for the module
logger = logging.getLogger(__name__)

def main() -> None:
    """
    Main function to parse arguments, handle shell completion,
    and orchestrate the Kubernetes debug container launch process.
    """
    # Argument Parsing
    parser = argparse.ArgumentParser(
        description="Launch a privileged debug container in a Kubernetes cluster.",
        epilog="""
            This tool uses fzf for interactive selection if kubectl and fzf are available.
            Example: ks -n my-namespace -p my-pod
        """
    )
    parser.add_argument(
        "-C", "--context",
        help="Specify the kube context to use."
    )
    parser.add_argument(
        "-n", "--namespace",
        help="Specify the namespace."
    )
    parser.add_argument(
        "-p", "--pod",
        help="Specify the pod name."
    )
    parser.add_argument(
        "-c", "--container",
        help="Specify the container name."
    )
    parser.add_argument(
        "-i", "--image",
        default="obeoneorg/netshoot",
        help="Specify the debug image to use."
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("KS_DEBUG_PROFILE", "sysadmin"),
        help="Specify the security profile for the debug container."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the kubectl command instead of executing it."
    )
    parser.add_argument(
        "-l", "--log-level",
        default="info",
        choices=["debug", "info", "warn", "error"],
        help="Set the log level for output messages."
    )
    parser.add_argument(
        "--completion",
        choices=["bash", "zsh", "fish"],
        help="Generate shell completion script for the specified shell."
    )
    # Internal flags for shell completion, hidden from help output
    parser.add_argument("--_list-contexts", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-namespaces", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-pods", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-containers", action="store_true", help=argparse.SUPPRESS)
    # Capture all remaining arguments as the command to be executed in the debug container.
    # The '--' is used to clearly separate ks arguments from the command arguments.
    parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Command and arguments for the debug container. Use '--' to separate them from ks options.",
    )

    args = parser.parse_args()

    # Configure colored logging based on the specified log level
    coloredlogs.install(
        level=args.log_level.upper(),
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        logger=logging.getLogger()
    )

    # Handle shell completion script generation
    if args.completion:
        script_name = os.path.basename(sys.argv[0])
        print_completion_script(args.completion, script_name)
        sys.exit(0)

    # Handle internal completion listing requests
    if args._list_contexts:
        """List available Kubernetes contexts for shell completion."""
        init_k8s_client()
        print(" ".join(get_contexts()))
        sys.exit(0)
    if args._list_namespaces:
        """List namespaces for a given context for shell completion."""
        init_k8s_client(context=args.context)
        print(" ".join(get_namespaces(context_for_api=args.context)))
        sys.exit(0)
    if args._list_pods:
        """List pods within a given namespace and context for shell completion."""
        init_k8s_client(context=args.context)
        print(" ".join(get_pods(namespace=args.namespace, context_for_api=args.context)))
        sys.exit(0)
    if args._list_containers:
        """List containers within a given pod, namespace, and context for shell completion."""
        init_k8s_client(context=args.context)
        print(" ".join(get_containers(namespace=args.namespace, pod_name=args.pod, context_for_api=args.context)))
        sys.exit(0)

    # Perform pre-flight checks for necessary tools and libraries
    if not KUBERNETES_AVAILABLE:
        logger.error("Python kubernetes library not found. Please install it with 'pip install kubernetes'.")
        sys.exit(1)
    check_command_availability("kubectl")
    check_command_availability("fzf") # Ensure fzf is available for interactive selection

    # Interactive selection of Kubernetes resources if not specified via arguments
    try:
        # If context is provided, use it. Otherwise, the client will use the current context.
        selected_context = args.context
        init_k8s_client(context=selected_context)

        selected_namespace = args.namespace or fzf_select(get_namespaces(context_for_api=selected_context), "Select Namespace")
        if not selected_namespace:
            logger.info("No namespace selected. Exiting.")
            sys.exit(0)

        selected_pod = args.pod or fzf_select(get_pods(namespace=selected_namespace, context_for_api=selected_context), "Select Pod")
        if not selected_pod:
            logger.info("No pod selected. Exiting.")
            sys.exit(0)

        # Fetch containers for the selected pod
        containers = get_containers(namespace=selected_namespace, pod_name=selected_pod, context_for_api=selected_context)
        if not containers:
            logger.error("No containers found in pod '%s'. Exiting.", selected_pod)
            sys.exit(1)

        selected_container = args.container
        if not selected_container:
            if len(containers) == 1:
                selected_container = containers[0]
                logger.info("Automatically selected the only container: %s", selected_container)
            else:
                selected_container = fzf_select(containers, "Select Container")

        if not selected_container:
            logger.info("No container selected. Exiting.")
            sys.exit(0)

    except Exception as e:
        logger.error("An error occurred during interactive selection: %s", e, exc_info=True)
        sys.exit(1)


    # Manage namespace security labels for privileged access
    label_applied = False
    if not check_namespace_label(namespace=selected_namespace, context_for_api=selected_context):
        logger.info("Applying 'privileged' Pod Security Admission label to namespace '%s'.", selected_namespace)
        if apply_namespace_label(namespace=selected_namespace, context_for_api=selected_context):
            label_applied = True
            # Register cleanup function to remove the label on exit
            register_cleanup(remove_namespace_label, namespace=selected_namespace, context_for_api=selected_context)
        else:
            logger.error("Failed to apply privileged label to namespace '%s'. Exiting.", selected_namespace)
            sys.exit(1)
    else:
        logger.info("Namespace '%s' already has the 'privileged' label.", selected_namespace)

    # Construct and execute the kubectl debug command
    debug_pod_name = f"debug-{selected_pod}-{uuid.uuid4().hex[:6]}"
    
    kubectl_command = ["kubectl", "debug", "-it"]
    if selected_context:
        kubectl_command.extend(["--context", selected_context])
        
    kubectl_command.extend([
        "-n", selected_namespace,
        selected_pod,
        "--target", selected_container,
        "--image", args.image,
        "--container", debug_pod_name,
        "--profile", args.profile,
        "--image-pull-policy=Always",
        "--share-processes",
    ])

    # Append the command and its arguments to the kubectl command
    if args.command_args:
        command_to_run = args.command_args
        # argparse with REMAINDER may include a leading '--', which should be removed
        if command_to_run and command_to_run[0] == '--':
            command_to_run.pop(0)

        if command_to_run:
            kubectl_command.append("--")
            kubectl_command.extend(command_to_run)
    
    logger.info("Generated kubectl command: %s", " ".join(kubectl_command))

    if args.dry_run:
        print(" ".join(kubectl_command))
    else:
        logger.info("Launching debug container...")
        # For an interactive command like kubectl debug, we run it without capturing output
        # so that the user's terminal can be attached to the process.
        run_command(kubectl_command, capture_output=False)

    # Execute registered cleanup functions (e.g., removing namespace label)
    if label_applied:
        logger.info("Running cleanup tasks...")
        run_cleanup()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting.")
        sys.exit(0)
