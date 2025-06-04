#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utility script to launch a privileged debug container in Kubernetes."""

import argparse
import json
import logging
import os
import sys
import uuid
import coloredlogs
from typing import Optional

from .completion import print_completion_script
from .helpers import (
    run_command,
    fzf_select,
    register_cleanup,
    run_cleanup,
)
from .k8s import (
    ApiException,
    KUBERNETES_AVAILABLE,
    apply_namespace_label,
    check_namespace_label,
    get_containers,
    get_contexts,
    get_namespaces,
    get_pod_metadata_display,
    get_pods,
    get_pods_with_node_display,
    init_k8s_client,
    k8s_client_initialized_ctx,
    remove_namespace_label,
)

# --- Configuration ---
DEFAULT_DEBUG_IMAGE = "harbor.obeone.cloud/public/netshoot:debian-podman"
LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}
SCRIPT_NAME = "ks"

# --- Logger Setup ---
logger = logging.getLogger()


def main() -> None:
    """Main entrypoint."""
    parser = argparse.ArgumentParser(
        description="Kubernetes Debug Helper Script. Helps in launching a debug container targeting a specific application container within a pod.",
        epilog=f"Example: {SCRIPT_NAME} -n my-namespace -p my-app-pod-xxxx -c my-app-container",
        add_help=False,
    )
    k8s_group = parser.add_argument_group("Kubernetes Target Options")
    k8s_group.add_argument("-C", "--context", help="Specify Kubernetes context to use")
    k8s_group.add_argument("-n", "--namespace", help="Specify namespace (interactive if not provided)")
    k8s_group.add_argument("-p", "--pod", help="Specify pod name (interactive if not provided)")
    k8s_group.add_argument(
        "-c", "--container", help="Specify container name (interactive if not provided, or auto if single)"
    )

    debug_group = parser.add_argument_group("Debug Session Options")
    debug_group.add_argument(
        "-i",
        "--image",
        default=DEFAULT_DEBUG_IMAGE,
        help=f"Debug container image to use (default: {DEFAULT_DEBUG_IMAGE})",
    )
    debug_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the kubectl debug command that would be run, without executing it",
    )

    behavior_group = parser.add_argument_group("Script Behavior Options")
    behavior_group.add_argument(
        "-l",
        "--log-level",
        choices=LOG_LEVEL_MAP.keys(),
        default="warn",
        help="Set log level (default: warn)",
    )
    behavior_group.add_argument(
        "-h", "--help", action="help", default=argparse.SUPPRESS, help="Show this help message and exit"
    )

    parser.add_argument("--completion", choices=["bash", "zsh", "fish"], help=argparse.SUPPRESS)
    parser.add_argument("--_list-contexts", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-namespaces", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-pods", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_list-containers", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Setup logging
    log_level_const = LOG_LEVEL_MAP.get(args.log_level, logging.WARNING)
    coloredlogs.install(
        level=log_level_const,
        logger=logger,
        fmt="[%(levelname)s] %(message)s",
        level_styles=coloredlogs.DEFAULT_LEVEL_STYLES,
        field_styles=coloredlogs.DEFAULT_FIELD_STYLES,
    )
    logger.debug("Log level set to %s", args.log_level.upper())

    if any([args._list_contexts, args._list_namespaces, args._list_pods, args._list_containers]):
        if not KUBERNETES_AVAILABLE:
            logger.error("Cannot generate dynamic completions: Kubernetes library not installed.")
            sys.exit(1)

    cb_context_arg = args.context
    if args._list_contexts:
        print("\n".join(get_contexts()))
        sys.exit(0)
    if args._list_namespaces:
        print("\n".join(get_namespaces(context_for_api=cb_context_arg)))
        sys.exit(0)
    if args._list_pods:
        if not args.namespace:
            logger.debug("Namespace required for pod listing in completion mode.")
            sys.exit(1)
        print("\n".join(get_pods(args.namespace, context_for_api=cb_context_arg)))
        sys.exit(0)
    if args._list_containers:
        if not args.namespace or not args.pod:
            logger.debug("Namespace and Pod required for container listing in completion mode.")
            sys.exit(1)
        print(
            "\n".join(get_containers(args.namespace, args.pod, context_for_api=cb_context_arg))
        )
        sys.exit(0)

    if not KUBERNETES_AVAILABLE:
        logger.error(
            "Fatal: Python Kubernetes client library is required but not installed. Please install 'kubernetes'."
        )
        sys.exit(1)

    if not init_k8s_client(context=args.context):
        sys.exit(1)
    logger.debug("K8s client initialized for main execution.")

    context_arg = args.context
    namespace = args.namespace
    pod_name = args.pod
    container_name = args.container
    debug_image = args.image
    dry_run = args.dry_run

    try:
        if not namespace:
            namespaces_list = get_namespaces(context_for_api=context_arg)
            if not namespaces_list:
                logger.error("No namespaces found or accessible.")
                sys.exit(1)
            selected_ns = fzf_select(namespaces_list, "Select Namespace > ")
            if not selected_ns:
                logger.error("No namespace selected. Aborting.")
                sys.exit(1)
            namespace = selected_ns
        logger.info("Using namespace: %s", namespace)

        if not pod_name:
            pods_with_nodes = get_pods_with_node_display(namespace, context_for_api=context_arg)
            if not pods_with_nodes:
                logger.error("No pods found in namespace '%s'.", namespace)
                sys.exit(1)
            selected_pod_line = fzf_select(pods_with_nodes, f"Select Pod in '{namespace}' > ")
            if not selected_pod_line:
                logger.error("No pod selected. Aborting.")
                sys.exit(1)
            pod_name = selected_pod_line.split()[0]
        logger.info("Using pod: %s", pod_name)

        if not container_name:
            containers_list = get_containers(namespace, pod_name, context_for_api=context_arg)
            if not containers_list:
                logger.error("No containers found in pod '%s'.", pod_name)
                sys.exit(1)
            if len(containers_list) == 1:
                container_name = containers_list[0]
                logger.info("Auto-selected only container: %s", container_name)
            else:
                selected_container = fzf_select(containers_list, f"Select Container in '{pod_name}' > ")
                if not selected_container:
                    logger.error("No container selected. Aborting.")
                    sys.exit(1)
                container_name = selected_container
        logger.info("Using container: %s", container_name)

        metadata = get_pod_metadata_display(
            namespace, pod_name, container_name, context_for_api=context_arg
        )
        if metadata:
            logger.info("Selected Target Metadata:")
            print(f"  Context:     {k8s_client_initialized_ctx or 'current (default)'}")
            print(f"  Pod:         {metadata['pod']}")
            print(f"  Namespace:   {metadata['namespace']}")
            print(f"  Node:        {metadata['node']}")
            print(f"  Container:   {metadata['container_name']}")
            print(f"  Image:       {metadata['image']}")
            resources_str = json.dumps(metadata.get("resources", {}), indent=4).replace("\n", "\n               ")
            print(f"  Resources:   {resources_str if metadata.get('resources') else 'Not set'}")
        else:
            logger.error(
                "Failed to retrieve metadata for %s/%s/%s. This might indicate the container was not found post-selection.",
                namespace,
                pod_name,
                container_name,
            )
            sys.exit(1)

        if not check_namespace_label(namespace, context_for_api=context_arg):
            logger.warning(
                "Namespace '%s' does not have the 'pod-security.kubernetes.io/enforce: privileged' label.",
                namespace,
            )
            logger.info(
                "This label might be required for 'kubectl debug --profile=sysadmin' to work correctly with Pod Security Admission."
            )
            if apply_namespace_label(namespace, context_for_api=context_arg):
                register_cleanup(remove_namespace_label, namespace, context_for_api=context_arg)
            else:
                logger.error("Failed to apply privileged label to namespace. Debug session may fail.")
        else:
            logger.info(
                "Namespace '%s' already has the required privileged label or equivalent.",
                namespace,
            )

        debug_session_id = str(uuid.uuid4())[:8]
        debug_container_name = f"debug-{container_name}-{debug_session_id}"

        kubectl_cmd_list = ["kubectl"]
        if context_arg:
            kubectl_cmd_list.extend(["--context", context_arg])
        kubectl_cmd_list.extend([
            "debug",
            pod_name,
            "--namespace",
            namespace,
            "--target",
            container_name,
            "--image",
            debug_image,
            "--image-pull-policy=Always",
            "-c",
            debug_container_name,
            "--profile=sysadmin",
            "--share-processes",
            "-ti",
        ])

        final_command_str = " ".join(kubectl_cmd_list)

        if dry_run:
            logger.info("[DRY RUN] Would execute: %s", final_command_str)
        else:
            logger.info(
                "Attempting to start debug session on '%s/%s/%s'...",
                namespace,
                pod_name,
                container_name,
            )
            logger.info("Executing: %s", final_command_str)
            run_command(kubectl_cmd_list, check=True, capture_output=False, text=False)
            logger.info("Debug session for '%s' finished.", debug_container_name)

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user (KeyboardInterrupt).")
        sys.exit(130)
    except SystemExit as e:
        if e.code not in [0, 1, 130]:
            logger.debug("Exiting script with code %s due to SystemExit.", e.code)
        raise
    except Exception as e:  # pylint: disable=broad-except
        logger.error("An unexpected error occurred in the main execution block: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        logger.debug("Main execution block finished or exited.")


if __name__ == "__main__":
    if "--completion" in sys.argv:
        try:
            idx = sys.argv.index("--completion")
            if idx + 1 < len(sys.argv):
                shell_type = sys.argv[idx + 1]
                if shell_type in ["bash", "zsh", "fish"]:
                    print_completion_script(shell_type, SCRIPT_NAME)
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
            pass

    main()
