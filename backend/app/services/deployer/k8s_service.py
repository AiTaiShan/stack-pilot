import logging
import time
from typing import Dict, List, Optional, Any

from app.core.error_handler import (
    AppError,
    ErrorCode,
    ErrorSeverity,
    handle_error,
    with_retry,
)

logger = logging.getLogger(__name__)


class K8sService:
    """Kubernetes 部署服务"""

    def __init__(self, kubeconfig: Optional[str] = None):
        self.kubeconfig = kubeconfig
        self._apps_v1 = None
        self._core_v1 = None
        self._networking_v1 = None
        self._client_initialized = False

    def _init_client(self):
        if self._client_initialized:
            return

        try:
            from kubernetes import client, config

            if self.kubeconfig:
                config.load_kube_config(config_file=self.kubeconfig)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

            self._apps_v1 = client.AppsV1Api()
            self._core_v1 = client.CoreV1Api()
            self._networking_v1 = client.NetworkingV1Api()
            self._client_initialized = True
        except ImportError:
            raise AppError(
                code=ErrorCode.K8S_ERROR,
                message="kubernetes package not installed",
                severity=ErrorSeverity.HIGH,
            )
        except Exception as e:
            raise AppError(
                code=ErrorCode.K8S_ERROR,
                message=f"Failed to initialize Kubernetes client: {e}",
                severity=ErrorSeverity.HIGH,
            )

    @property
    def apps_v1(self):
        self._init_client()
        return self._apps_v1

    @property
    def core_v1(self):
        self._init_client()
        return self._core_v1

    @property
    def networking_v1(self):
        self._init_client()
        return self._networking_v1

    @handle_error
    def create_namespace(self, namespace: str) -> None:
        from kubernetes.client import V1Namespace, V1ObjectMeta

        try:
            self.core_v1.read_namespace(namespace)
            logger.info("Namespace %s already exists", namespace)
            return
        except Exception:
            pass

        ns = V1Namespace(metadata=V1ObjectMeta(name=namespace))
        self.core_v1.create_namespace(ns)
        logger.info("Created namespace: %s", namespace)

    @handle_error
    @with_retry(config_name="k8s")
    def create_deployment(
        self,
        namespace: str,
        name: str,
        image: str,
        replicas: int = 1,
        port: int = 80,
        env_vars: Optional[Dict[str, str]] = None,
        resources: Optional[Dict[str, Any]] = None,
    ) -> None:
        from kubernetes.client import (
            V1Deployment,
            V1DeploymentSpec,
            V1PodTemplateSpec,
            V1PodSpec,
            V1Container,
            V1ContainerPort,
            V1EnvVar,
            V1ResourceRequirements,
            V1LabelSelector,
            V1ObjectMeta,
        )

        container_port = V1ContainerPort(container_port=port)
        env_list = [V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()]

        resource_req = None
        if resources:
            resource_req = V1ResourceRequirements(
                requests=resources.get("requests", {}),
                limits=resources.get("limits", {}),
            )

        container = V1Container(
            name=name,
            image=image,
            ports=[container_port],
            env=env_list,
            resources=resource_req,
        )

        template = V1PodTemplateSpec(
            metadata=V1ObjectMeta(labels={"app": name}),
            spec=V1PodSpec(containers=[container]),
        )

        selector = V1LabelSelector(match_labels={"app": name})

        spec = V1DeploymentSpec(
            replicas=replicas,
            template=template,
            selector=selector,
        )

        deployment = V1Deployment(
            metadata=V1ObjectMeta(name=name),
            spec=spec,
        )

        try:
            self.apps_v1.read_namespaced_deployment(name, namespace)
            self.apps_v1.replace_namespaced_deployment(name, namespace, deployment)
            logger.info("Updated deployment %s in namespace %s", name, namespace)
        except Exception:
            self.apps_v1.create_namespaced_deployment(namespace, deployment)
            logger.info("Created deployment %s in namespace %s", name, namespace)

    @handle_error
    def create_service(
        self,
        namespace: str,
        name: str,
        port: int = 80,
        target_port: int = 80,
        service_type: str = "ClusterIP",
    ) -> None:
        from kubernetes.client import (
            V1Service,
            V1ServiceSpec,
            V1ServicePort,
            V1ObjectMeta,
        )

        service_port = V1ServicePort(
            port=port,
            target_port=target_port,
            protocol="TCP",
        )

        spec = V1ServiceSpec(
            type=service_type,
            ports=[service_port],
            selector={"app": name},
        )

        service = V1Service(
            metadata=V1ObjectMeta(name=name),
            spec=spec,
        )

        try:
            self.core_v1.read_namespaced_service(name, namespace)
            self.core_v1.replace_namespaced_service(name, namespace, service)
            logger.info("Updated service %s in namespace %s", name, namespace)
        except Exception:
            self.core_v1.create_namespaced_service(namespace, service)
            logger.info("Created service %s in namespace %s", name, namespace)

    @handle_error
    def create_ingress(
        self,
        namespace: str,
        name: str,
        host: str,
        service_name: str,
        service_port: int,
        tls: bool = False,
    ) -> None:
        from kubernetes.client import (
            V1Ingress,
            V1IngressSpec,
            V1IngressRule,
            V1IngressBackend,
            V1IngressServiceBackend,
            V1ServiceBackendPort,
            V1HTTPIngressPath,
            V1HTTPIngressRuleValue,
            V1IngressTLS,
            V1ObjectMeta,
        )

        backend = V1IngressBackend(
            service=V1IngressServiceBackend(
                name=service_name,
                port=V1ServiceBackendPort(number=service_port),
            )
        )

        path = V1HTTPIngressPath(
            path="/",
            path_type="Prefix",
            backend=backend,
        )

        rule = V1IngressRule(
            host=host,
            http=V1HTTPIngressRuleValue(paths=[path]),
        )

        tls_config = None
        if tls:
            tls_config = [V1IngressTLS(hosts=[host], secret_name=f"{name}-tls")]

        spec = V1IngressSpec(
            rules=[rule],
            tls=tls_config,
        )

        ingress = V1Ingress(
            metadata=V1ObjectMeta(
                name=name,
                annotations={
                    "nginx.ingress.kubernetes.io/rewrite-target": "/",
                },
            ),
            spec=spec,
        )

        try:
            self.networking_v1.read_namespaced_ingress(name, namespace)
            self.networking_v1.replace_namespaced_ingress(name, namespace, ingress)
            logger.info("Updated ingress %s in namespace %s", name, namespace)
        except Exception:
            self.networking_v1.create_namespaced_ingress(namespace, ingress)
            logger.info("Created ingress %s in namespace %s", name, namespace)

    @handle_error
    def get_deployment_status(self, namespace: str, name: str) -> Dict[str, Any]:
        deployment = self.apps_v1.read_namespaced_deployment(name, namespace)

        ready_replicas = deployment.status.ready_replicas or 0
        total_replicas = deployment.spec.replicas or 0

        if ready_replicas == total_replicas and total_replicas > 0:
            status = "ready"
        elif deployment.status.unavailable_replicas:
            status = "unavailable"
        else:
            status = "pending"

        return {
            "name": name,
            "namespace": namespace,
            "status": status,
            "ready_replicas": ready_replicas,
            "total_replicas": total_replicas,
            "updated_replicas": deployment.status.updated_replicas or 0,
        }

    @handle_error
    def delete_deployment(self, namespace: str, name: str) -> None:
        try:
            self.apps_v1.delete_namespaced_deployment(name, namespace)
            logger.info("Deleted deployment %s from namespace %s", name, namespace)
        except Exception as e:
            logger.warning("Failed to delete deployment: %s", e)

        try:
            self.core_v1.delete_namespaced_service(name, namespace)
            logger.info("Deleted service %s from namespace %s", name, namespace)
        except Exception:
            pass

        try:
            self.networking_v1.delete_namespaced_ingress(name, namespace)
            logger.info("Deleted ingress %s from namespace %s", name, namespace)
        except Exception:
            pass

    @handle_error
    def wait_for_deployment(
        self,
        namespace: str,
        name: str,
        timeout: int = 300,
        interval: int = 5,
    ) -> Dict[str, Any]:
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_deployment_status(namespace, name)
            if status["status"] == "ready":
                logger.info("Deployment %s is ready", name)
                return status
            elif status["status"] == "unavailable":
                logger.warning("Deployment %s is unavailable", name)

            time.sleep(interval)

        raise AppError(
            code=ErrorCode.TIMEOUT_ERROR,
            message=f"Deployment {name} not ready within {timeout}s",
            severity=ErrorSeverity.HIGH,
            retryable=False,
        )
