# -*- coding: utf-8 -*-
"""
Kubernetes API interaction module.

This module abstracts all interactions with the Kubernetes API, providing
functions to initialize the client, list resources (contexts, namespaces, pods,
containers), and manage resource labels. It gracefully handles the absence of
the 'kubernetes' Python package, allowing the application to provide helpful
error messages.
"""

import sys
import json
import logging
from typing import List, Optional, Dict, Any

try:
    # Attempt to import Kubernetes client libraries.
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException
    KUBERNETES_AVAILABLE = True
except ImportError:  # pragma: no cover - This block runs if 'kubernetes' is not installed.
    KUBERNETES_AVAILABLE = False

    class _PlaceholderApiException(Exception):  # type: ignore
        """A placeholder for ApiException if the 'kubernetes' package is not installed."""
        def __init__(self, status: int = 0, reason: str = "") -> None:
            super().__init__(reason)
            self.status = status
            self.reason = reason
            self.body = None
            self.headers = None

    # Alias the placeholder to ensure type consistency throughout the module.
    ApiException = _PlaceholderApiException  # type: ignore

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Module-level Globals for Kubernetes Client ---
# Holds the initialized CoreV1Api client instance.
core_v1_api: Optional['client.CoreV1Api'] = None
# Stores the context name for which the client was last initialized.
k8s_client_initialized_ctx: Optional[str] = None


def init_k8s_client(context: Optional[str] = None, force_reload: bool = False) -> bool:
    """
    Initializes the Kubernetes API client for a specific context.

    This function loads the kubeconfig and sets up the CoreV1Api client. It avoids
    re-initialization if the client is already configured for the requested context,
    unless `force_reload` is True.

    Args:
        context: The name of the Kubernetes context to use. If None, the default
                 context from kubeconfig is used.
        force_reload: If True, forces a reload of the client even if it's already
                      initialized for the same context.

    Returns:
        True if the client was successfully initialized, False otherwise.
    """
    global core_v1_api, k8s_client_initialized_ctx

    # Avoid re-initialization if already configured for the same context.
    if (
        k8s_client_initialized_ctx is not None
        and k8s_client_initialized_ctx == context
        and not force_reload
    ):
        logger.debug("Kubernetes client already initialized for context: %s", context)
        return core_v1_api is not None

    logger.info("Initializing Kubernetes client for context: %s (force_reload=%s)", context or "default", force_reload)

    if not KUBERNETES_AVAILABLE:
        # Log error if the library is missing.
        if logger.handlers:
            logger.error("Kubernetes library is required but not installed. Please run 'pip install kubernetes'.")
        else:
            # Fallback to stderr if logging is not yet configured.
            print(
                "[ERROR] Kubernetes library is required but not installed. Please run 'pip install kubernetes'.",
                file=sys.stderr,
            )
        return False

    try:
        logger.debug("Loading Kubernetes configuration for context: %s", context or "default")
        config.load_kube_config(context=context)
        core_v1_api = client.CoreV1Api()
        k8s_client_initialized_ctx = context
        logger.debug("Kubernetes client initialized successfully for context: %s", context or "current")
        return True
    except ConfigException as e:
        logger.error("Kubernetes config error for context '%s': %s", context or "default", e)
        core_v1_api = None
        k8s_client_initialized_ctx = None
        if not any(arg.startswith('--_list') for arg in sys.argv) and '--completion' not in sys.argv:
            sys.exit(1)
        return False
    except Exception as e:  # pylint: disable=broad-except
        logger.error("An unexpected error occurred during Kubernetes client initialization for context '%s': %s", context or "default", e, exc_info=True)
        core_v1_api = None
        k8s_client_initialized_ctx = None
        # Suppress exit for completion and internal listing commands.
        if not any(arg.startswith('--_list') for arg in sys.argv) and '--completion' not in sys.argv:
            sys.exit(1)
        return False


def get_contexts() -> List[str]:
    """
    Retrieves a sorted list of available Kubernetes contexts from the kubeconfig file.

    Returns:
        A list of context names, or an empty list if an error occurs or the
        Kubernetes library is not available.
    """
    if not KUBERNETES_AVAILABLE:
        return []
    try:
        contexts_list, _ = config.list_kube_config_contexts()
        # The context object is a dictionary with a 'name' key.
        return sorted(ctx.get('name', '') for ctx in contexts_list if isinstance(ctx, dict) and ctx.get('name'))
    except (ConfigException, Exception) as e:  # pylint: disable=broad-except
        logger.error("Failed to list kubeconfig contexts: %s", e)
        return []


def get_namespaces(context_for_api: Optional[str] = None) -> List[str]:
    """
    Lists all namespaces in the cluster for a given context.

    Args:
        context_for_api: The Kubernetes context to use for the API call.

    Returns:
        A sorted list of namespace names, or an empty list on failure.
    """
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            namespaces = core_v1_api.list_namespace()
            return sorted(
                ns.metadata.name
                for ns in namespaces.items
                if ns.metadata and ns.metadata.name
            )
        except ApiException as e:
            logger.error("API error listing namespaces: %s %s", e.status, e.reason)
    return []


def get_pods(namespace: str, context_for_api: Optional[str] = None) -> List[str]:
    """
    Lists all pods within a specific namespace.

    Args:
        namespace: The namespace from which to list pods.
        context_for_api: The Kubernetes context to use for the API call.

    Returns:
        A sorted list of pod names, or an empty list on failure.
    """
    if namespace and init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pods = core_v1_api.list_namespaced_pod(namespace=namespace)
            return sorted(
                pod.metadata.name
                for pod in pods.items
                if pod.metadata and pod.metadata.name
            )
        except ApiException as e:
            logger.error(
                "API error listing pods in namespace '%s': %s %s", namespace, e.status, e.reason
            )
    return []


def get_containers(
    namespace: str, pod_name: str, context_for_api: Optional[str] = None
) -> List[str]:
    """
    Lists all container names for a specific pod.

    Args:
        namespace: The namespace of the pod.
        pod_name: The name of the pod.
        context_for_api: The Kubernetes context to use for the API call.

    Returns:
        A list of container names, or an empty list if the pod or containers
        are not found or an API error occurs.
    """
    if namespace and pod_name and init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pod: Any = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod and hasattr(pod, 'spec') and pod.spec and hasattr(pod.spec, 'containers') and pod.spec.containers:
                return [c.name for c in pod.spec.containers]
        except ApiException as e:
            if e.status != 404:
                logger.error(
                    "API error reading pod '%s' to get containers: %s %s",
                    pod_name,
                    e.status,
                    e.reason,
                )
    return []


def handle_api_exception_norm(e: Any, operation_desc: str) -> None:
    """
    Logs a standardized error message for a Kubernetes ApiException and exits.

    Args:
        e: The ApiException instance.
        operation_desc: A description of the operation that failed.
    """
    logger.error(
        "API error during '%s': Status %s, Reason: %s", operation_desc, e.status, e.reason
    )
    if e.body:
        try:
            error_body = json.loads(e.body)
            logger.error("Details: %s", error_body.get('message', e.body))
        except (json.JSONDecodeError, TypeError):
            logger.error("Details (raw): %s", e.body)

    # Provide actionable suggestions based on the HTTP status code.
    if e.status == 403:
        logger.error("Suggestion: Check RBAC permissions for the current user/service account.")
    elif e.status == 404:
        logger.error(
            "Suggestion: Verify that the targeted Kubernetes resource exists and that the names are correct."
        )
    sys.exit(1)


def get_pods_with_node_display(
    namespace: str, context_for_api: Optional[str] = None
) -> List[str]:
    """
    Lists pods in a namespace, formatted with their assigned node names.

    Args:
        namespace: The namespace to query for pods.
        context_for_api: The Kubernetes context to use.

    Returns:
        A list of strings, where each string is "pod_name node_name".
    """
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
            handle_api_exception_norm(e, f"list pods in namespace '{namespace}'")
    return pods_info


def get_pod_metadata_display(
    namespace: str,
    pod_name: str,
    container_name: str,
    context_for_api: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieves detailed metadata for a specific pod and container.

    This includes pod name, namespace, node, container image, resource limits/requests,
    and the effective user/group IDs from the security context.

    Args:
        namespace: The namespace of the pod.
        pod_name: The name of the pod.
        container_name: The name of the container within the pod.
        context_for_api: The Kubernetes context to use.

    Returns:
        A dictionary containing the metadata, or None if the resource cannot be
        found or an error occurs.
    """
    if not init_k8s_client(context=context_for_api) or not core_v1_api:
        logger.error("Aborting metadata retrieval: K8s client not initialized.")
        return None

    try:
        logger.debug("Reading pod '%s' in namespace '%s'", pod_name, namespace)
        pod: Any = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)

        if not pod or not hasattr(pod, 'spec') or not pod.spec:
            logger.error("Could not retrieve a valid pod spec for '%s'.", pod_name)
            return None

        logger.debug("Searching for container '%s' in pod '%s'", container_name, pod_name)
        selected_container_obj = next(
            (c for c in (pod.spec.containers or []) if c.name == container_name),
            None,
        )

        if not selected_container_obj:
            logger.warning("Container '%s' not found in pod '%s'.", container_name, pod_name)
            return None
        logger.debug("Found container '%s'.", container_name)

        # Extract resource limits and requests safely.
        resources_dict = {}
        if hasattr(selected_container_obj, 'resources') and selected_container_obj.resources:
            resources_dict['limits'] = selected_container_obj.resources.limits or {}
            resources_dict['requests'] = selected_container_obj.resources.requests or {}
        
        # Determine effective security context (container overrides pod).
        pod_sc = pod.spec.security_context or {}
        container_sc = selected_container_obj.security_context or {}
        
        run_as_user = container_sc.get('run_as_user', pod_sc.get('run_as_user'))
        run_as_group = container_sc.get('run_as_group', pod_sc.get('run_as_group'))

        metadata = {
            "pod": getattr(pod.metadata, 'name', 'N/A'),
            "namespace": getattr(pod.metadata, 'namespace', 'N/A'),
            "node": getattr(pod.spec, 'node_name', 'N/A'),
            "container_name": getattr(selected_container_obj, 'name', 'N/A'),
            "image": getattr(selected_container_obj, 'image', 'N/A'),
            "resources": client.ApiClient().sanitize_for_serialization(resources_dict),
            "run_as_user": run_as_user,
            "run_as_group": run_as_group,
        }
        logger.debug("Successfully assembled pod metadata: %s", metadata)
        return metadata

    except ApiException as e:
        handle_api_exception_norm(e, f"read pod '{pod_name}' in namespace '{namespace}'")
        return None
    except Exception as e:
        logger.error("An unexpected error occurred while getting pod metadata: %s", e, exc_info=True)
        return None


def check_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    """
    Checks if a namespace has the 'pod-security.kubernetes.io/enforce: privileged' label.

    Args:
        namespace: The namespace to check.
        context_for_api: The Kubernetes context to use.

    Returns:
        True if the label is present and set to 'privileged', False otherwise.
    """
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            ns_obj: Any = core_v1_api.read_namespace(name=namespace)
            if ns_obj and hasattr(ns_obj, 'metadata') and ns_obj.metadata and hasattr(ns_obj.metadata, 'labels') and ns_obj.metadata.labels:
                label_value = ns_obj.metadata.labels.get("pod-security.kubernetes.io/enforce")
                return label_value == "privileged"
        except ApiException as e:
            if e.status == 404:
                logger.error("Namespace '%s' not found.", namespace)
                sys.exit(1)
            else:
                handle_api_exception_norm(e, f"read namespace '{namespace}'")
    return False


def apply_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    """
    Applies the 'pod-security.kubernetes.io/enforce: privileged' label to a namespace.

    Args:
        namespace: The namespace to label.
        context_for_api: The Kubernetes context to use.

    Returns:
        True if the label was applied successfully, False otherwise.
    """
    if init_k8s_client(context=context_for_api) and core_v1_api:
        logger.warning(
            "Applying 'pod-security.kubernetes.io/enforce: privileged' label to namespace '%s'.",
            namespace,
        )
        patch_body = {"metadata": {"labels": {"pod-security.kubernetes.io/enforce": "privileged"}}}
        try:
            core_v1_api.patch_namespace(name=namespace, body=patch_body)
            logger.info("Successfully applied privileged label to namespace '%s'.", namespace)
            return True
        except ApiException as e:
            handle_api_exception_norm(e, f"patch namespace '{namespace}' to apply label")
    return False


def remove_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> None:
    """
    Removes the 'pod-security.kubernetes.io/enforce' label from a namespace.

    This function is typically registered as a cleanup task to revert changes
    made during the script's execution. It handles cases where the label may
    already be gone.

    Args:
        namespace: The namespace from which to remove the label.
        context_for_api: The Kubernetes context to use.
    """
    if init_k8s_client(context=context_for_api) and core_v1_api:
        logger.info(
            "Attempting to remove 'pod-security.kubernetes.io/enforce' label from namespace '%s'.",
            namespace,
        )
        # The key must be escaped for a JSON patch operation.
        label_key_for_patch = "pod-security.kubernetes.io~1enforce"
        patch_body = [{"op": "remove", "path": f"/metadata/labels/{label_key_for_patch}"}]

        try:
            core_v1_api.patch_namespace(name=namespace, body=patch_body)
            logger.info(
                "Label 'pod-security.kubernetes.io/enforce' removed from namespace '%s'.",
                namespace,
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning("Namespace '%s' not found during label removal attempt.", namespace)
            elif e.status in [400, 422]:
                # These errors often mean the label was already gone.
                error_msg = f"API error ({e.status}) during label removal for '{namespace}'"
                if e.body:
                    try:
                        error_details = json.loads(e.body)
                        msg_lower = str(error_details.get("message", "")).lower()
                        # Check for common messages indicating the label is already absent.
                        if (
                            "remove operation does not apply" in msg_lower
                            or "path does not exist" in msg_lower
                            or "not found" in msg_lower
                            or "testPath path does not exist" in msg_lower
                        ):
                            logger.debug(
                                "Label '%s' was likely already absent from namespace '%s'.",
                                label_key_for_patch.replace("~1", "/"),
                                namespace,
                            )
                        else:
                            logger.warning("%s. Details: %s", error_msg, error_details.get("message", e.body))
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("%s. Raw body: %s", error_msg, e.body)
                else:
                    logger.warning(error_msg)
            else:
                # Log other, unexpected API errors.
                logger.warning(
                    "Unexpected API error during label removal for namespace '%s': %s %s",
                    namespace,
                    e.status,
                    e.reason,
                )
                if e.body:
                    logger.warning("Error body: %s", e.body)
    else:
        logger.warning(
            "Cannot remove label for '%s': Kubernetes client is unavailable or not initialized.",
            namespace,
        )
