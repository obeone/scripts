import sys
import json
import logging
from typing import List, Optional, Dict, Any

try:
    from kubernetes import client, config
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException
    KUBERNETES_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    KUBERNETES_AVAILABLE = False
    class ApiException(Exception):  # type: ignore
        """Placeholder ApiException if kubernetes package is missing."""
        def __init__(self, status: int = 0, reason: str = "") -> None:
            super().__init__(reason)
            self.status = status
            self.reason = reason
            self.body = None
            self.headers = None

logger = logging.getLogger(__name__)

core_v1_api: Optional['client.CoreV1Api'] = None
k8s_client_initialized_ctx: Optional[str] = None


def init_k8s_client(context: Optional[str] = None, force_reload: bool = False) -> bool:
    """Initialize the Kubernetes API client."""
    global core_v1_api, k8s_client_initialized_ctx
    if (
        k8s_client_initialized_ctx is not None
        and k8s_client_initialized_ctx == context
        and not force_reload
    ):
        return core_v1_api is not None

    if not KUBERNETES_AVAILABLE:
        if logger.handlers:
            logger.error("Kubernetes library is required but not installed.")
        else:
            print(
                "[ERROR] Kubernetes library is required but not installed.",
                file=sys.stderr,
            )
        return False
    try:
        logger.debug("Loading K8s config (context: %s)", context or "default")
        config.load_kube_config(context=context)
        core_v1_api = client.CoreV1Api()
        k8s_client_initialized_ctx = context
        return True
    except (ConfigException, Exception) as e:  # pylint: disable=broad-except
        logger.error("K8s client init failed (context: %s): %s", context, e)
        core_v1_api = None
        k8s_client_initialized_ctx = None
        if not any(arg.startswith('--_list') for arg in sys.argv) and '--completion' not in sys.argv:
            sys.exit(1)
        return False


def get_contexts() -> List[str]:
    """Return available Kubernetes contexts."""
    if not KUBERNETES_AVAILABLE:
        return []
    try:
        contexts_list, _ = config.list_kube_config_contexts()
        return sorted(ctx['name'] for ctx in contexts_list)
    except (ConfigException, Exception) as e:  # pylint: disable=broad-except
        logger.error("Failed to list kubeconfig contexts: %s", e)
        return []


def get_namespaces(context_for_api: Optional[str] = None) -> List[str]:
    """List namespaces for a given context."""
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
    """List pods in a namespace."""
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
                "API error listing pods in ns %s: %s %s", namespace, e.status, e.reason
            )
    return []


def get_containers(
    namespace: str, pod_name: str, context_for_api: Optional[str] = None
) -> List[str]:
    """List containers for a pod."""
    if namespace and pod_name and init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.spec and pod.spec.containers:
                return [c.name for c in pod.spec.containers]
        except ApiException as e:
            if e.status != 404:
                logger.error(
                    "API error reading pod %s to get containers: %s %s",
                    pod_name,
                    e.status,
                    e.reason,
                )
    return []


def handle_api_exception_norm(e: ApiException, operation_desc: str) -> None:
    """Log Kubernetes ApiException and exit."""
    logger.error(
        "API error during '%s': Status %s, Reason: %s", operation_desc, e.status, e.reason
    )
    if e.body:
        try:
            error_body = json.loads(e.body)
            logger.error("Details: %s", error_body.get('message', e.body))
        except json.JSONDecodeError:
            logger.error("Details (raw): %s", e.body)
    if e.status == 403:
        logger.error("Suggestion: Check RBAC permissions for the K8s user/service account.")
    elif e.status == 404:
        logger.error(
            "Suggestion: Check if the targeted Kubernetes resource exists and names are correct."
        )
    sys.exit(1)


def get_pods_with_node_display(
    namespace: str, context_for_api: Optional[str] = None
) -> List[str]:
    """List pods with their node names."""
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
    return pods_info


def get_pod_metadata_display(
    namespace: str,
    pod_name: str,
    container_name: str,
    context_for_api: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return detailed pod/container metadata."""
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            selected_container_obj = next(
                (c for c in (pod.spec.containers or []) if c.name == container_name),
                None,
            )

            if not selected_container_obj:
                logger.warning("Container '%s' not found in pod '%s'.", container_name, pod_name)
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
                "resources": client.ApiClient().sanitize_for_serialization(resources_dict)
                or {},
            }
            return metadata
        except ApiException as e:
            handle_api_exception_norm(e, f"read pod {pod_name} in namespace {namespace}")
            return None
    return None


def check_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    """Check if namespace has the privileged label."""
    if init_k8s_client(context=context_for_api) and core_v1_api:
        try:
            ns_obj = core_v1_api.read_namespace(name=namespace)
            if ns_obj.metadata and ns_obj.metadata.labels:
                label_value = ns_obj.metadata.labels.get("pod-security.kubernetes.io/enforce")
                return label_value == "privileged"
        except ApiException as e:
            if e.status == 404:
                logger.error("Namespace '%s' not found.", namespace)
                sys.exit(1)
            else:
                handle_api_exception_norm(e, f"read namespace {namespace}")
    return False


def apply_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> bool:
    """Apply privileged label to a namespace."""
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
            handle_api_exception_norm(e, f"patch namespace {namespace} to apply label")
    return False


def remove_namespace_label(namespace: str, context_for_api: Optional[str] = None) -> None:
    """Remove the privileged label from a namespace if present."""
    if init_k8s_client(context=context_for_api) and core_v1_api:
        logger.info(
            "Attempting to remove 'pod-security.kubernetes.io/enforce' label from namespace '%s'.",
            namespace,
        )
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
                logger.warning("Namespace '%s' not found during label removal attempt.", namespace)
            elif e.status in [400, 422]:
                error_msg = f"API error ({e.status}) during label removal for '{namespace}'"
                try:
                    error_details = json.loads(e.body)
                    msg_lower = str(error_details.get("message", "")).lower()
                    if (
                        "remove operation does not apply" in msg_lower
                        or "path does not exist" in msg_lower
                        or "not found" in msg_lower
                        or "testPath path does not exist" in msg_lower
                    ):
                        logger.debug(
                            "Label '%s' likely already removed or never existed on namespace '%s'. Details: %s",
                            label_key_for_patch.replace("~1", "/"),
                            namespace,
                            msg_lower,
                        )
                    else:
                        logger.warning("%s. Details: %s", error_msg, error_details.get("message", e.body))
                except json.JSONDecodeError:
                    logger.warning("%s. Raw body: %s", error_msg, e.body)
            else:
                logger.warning(
                    "API error during label removal for namespace '%s': %s %s",
                    namespace,
                    e.status,
                    e.reason,
                )
                if e.body:
                    logger.warning("Error body: %s", e.body)
    else:
        logger.warning(
            "Cannot remove label for '%s': K8s client unavailable or not initialized for context.",
            namespace,
        )
