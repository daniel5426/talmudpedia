from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse


logger = logging.getLogger("artifact.runtime.bootstrap")

_LOCAL_DIFYSANDBOX_STARTED_BY_APP = False
_LOCAL_DIFYSANDBOX_CONTAINER_NAME = ""
_LOCAL_ARTIFACT_WORKER_STARTED_BY_APP = False
_LOCAL_ARTIFACT_WORKER_PROCESS: subprocess.Popen | None = None


def configure_local_artifact_runtime_env_if_needed(*, auto_bootstrap_enabled: bool) -> None:
    if not auto_bootstrap_enabled:
        return

    worker_host = (os.getenv("LOCAL_ARTIFACT_WORKER_HOST") or "127.0.0.1").strip()
    worker_port = int((os.getenv("LOCAL_ARTIFACT_WORKER_PORT") or "8210").strip())
    sandbox_host = (os.getenv("LOCAL_DIFYSANDBOX_HOST") or "127.0.0.1").strip()
    sandbox_port = int((os.getenv("LOCAL_DIFYSANDBOX_PORT") or "8194").strip())

    os.environ.setdefault("ARTIFACT_WORKER_CLIENT_MODE", "http")
    os.environ.setdefault("ARTIFACT_WORKER_BASE_URL", f"http://{worker_host}:{worker_port}")
    os.environ.setdefault("ARTIFACT_WORKER_INTERNAL_TOKEN", "local-artifact-worker-token")
    os.environ.setdefault("ARTIFACT_WORKER_START_MODE", "http")
    os.environ.setdefault("ARTIFACT_RUN_TASK_EAGER", "0")
    os.environ.setdefault("ARTIFACT_SANDBOX_PROVIDER", "difysandbox")
    os.environ.setdefault("ARTIFACT_SANDBOX_TIMEOUT_SECONDS", "30")
    os.environ.setdefault("ARTIFACT_SANDBOX_WORKSPACE_PATH", "/workspace")
    os.environ.setdefault("ARTIFACT_SANDBOX_ALLOW_NETWORK", "0")
    os.environ.setdefault("ARTIFACT_SANDBOX_CLEANUP_ENABLED", "1")
    os.environ.setdefault(
        "ARTIFACT_WORKER_DEPENDENCY_CACHE_DIR",
        "/tmp/talmudpedia-artifact-runtime-cache/dependencies",
    )
    os.environ.setdefault("DIFYSANDBOX_API_BASE_URL", f"http://{sandbox_host}:{sandbox_port}")
    os.environ.setdefault("DIFYSANDBOX_API_KEY", os.getenv("LOCAL_DIFYSANDBOX_API_KEY", "dify-sandbox"))
    os.environ.setdefault("DIFYSANDBOX_TIMEOUT_SECONDS", os.getenv("ARTIFACT_SANDBOX_TIMEOUT_SECONDS", "30"))
    os.environ.setdefault(
        "DIFYSANDBOX_WORKSPACE_PATH",
        os.getenv("ARTIFACT_SANDBOX_WORKSPACE_PATH", "/workspace"),
    )


def ensure_local_artifact_runtime_infra_if_needed(*, auto_bootstrap_enabled: bool) -> None:
    if not auto_bootstrap_enabled:
        return
    _ensure_local_difysandbox_if_needed()
    _ensure_local_artifact_worker_service_if_needed()


def stop_local_artifact_runtime_infra_if_needed() -> None:
    _stop_local_artifact_worker_service_if_needed()
    _stop_local_difysandbox_if_needed()


def _ensure_local_difysandbox_if_needed() -> None:
    global _LOCAL_DIFYSANDBOX_STARTED_BY_APP, _LOCAL_DIFYSANDBOX_CONTAINER_NAME

    if not _is_truthy(os.getenv("LOCAL_DIFYSANDBOX_AUTO_BOOTSTRAP", "1")):
        return
    base_url = (os.getenv("DIFYSANDBOX_API_BASE_URL") or "").strip()
    if not base_url:
        host = (os.getenv("LOCAL_DIFYSANDBOX_HOST") or "127.0.0.1").strip()
        port = int((os.getenv("LOCAL_DIFYSANDBOX_PORT") or "8194").strip())
        base_url = f"http://{host}:{port}"
        os.environ["DIFYSANDBOX_API_BASE_URL"] = base_url

    parsed = _parse_endpoint_host_port(base_url)
    if not parsed:
        logger.warning("DifySandbox base URL is invalid: %s", base_url)
        return
    host, port = parsed
    if not _is_local_host(host):
        return
    if _is_port_open(host, port):
        logger.info("DifySandbox is already reachable at %s:%s", host, port)
        return
    if not _docker_available():
        logger.warning("Docker is unavailable; local DifySandbox auto-bootstrap is skipped")
        return

    image = (os.getenv("LOCAL_DIFYSANDBOX_IMAGE") or "langgenius/dify-sandbox:latest").strip()
    container_name = (os.getenv("LOCAL_DIFYSANDBOX_CONTAINER_NAME") or "talmudpedia-difysandbox-dev").strip()
    container_port = int((os.getenv("LOCAL_DIFYSANDBOX_CONTAINER_PORT") or "8194").strip())
    startup_timeout_seconds = float((os.getenv("LOCAL_DIFYSANDBOX_STARTUP_TIMEOUT_SECONDS") or "30").strip())
    api_key = (os.getenv("DIFYSANDBOX_API_KEY") or os.getenv("LOCAL_DIFYSANDBOX_API_KEY") or "dify-sandbox").strip()
    worker_timeout = (os.getenv("DIFYSANDBOX_TIMEOUT_SECONDS") or "30").strip()
    enable_network = "true" if _is_truthy(os.getenv("ARTIFACT_SANDBOX_ALLOW_NETWORK", "0")) else "false"

    _LOCAL_DIFYSANDBOX_CONTAINER_NAME = container_name

    inspect = _run_docker_command(
        ["ps", "-a", "--filter", f"name=^/{container_name}$", "--format", "{{.Names}}\t{{.Status}}"]
    )
    container_exists = container_name in (inspect.stdout or "")
    container_running = "Up " in (inspect.stdout or "")

    if not container_exists:
        docker_args = [
            "run",
            "-d",
            "--name",
            container_name,
            "-e",
            f"API_KEY={api_key}",
            "-e",
            f"SANDBOX_PORT={container_port}",
            "-e",
            f"WORKER_TIMEOUT={worker_timeout}",
            "-e",
            f"ENABLE_NETWORK={enable_network}",
            "-p",
            f"{port}:{container_port}",
        ]
        extra_args = (os.getenv("LOCAL_DIFYSANDBOX_EXTRA_DOCKER_ARGS") or "").strip()
        if extra_args:
            docker_args.extend(extra_args.split())
        docker_args.append(image)
        result = _run_docker_command(docker_args)
        if result.returncode != 0:
            logger.warning(
                "Failed to start local DifySandbox container `%s`: %s",
                container_name,
                (result.stderr or result.stdout).strip(),
            )
            return
        _LOCAL_DIFYSANDBOX_STARTED_BY_APP = True
    elif not container_running:
        start_result = _run_docker_command(["start", container_name])
        if start_result.returncode != 0:
            logger.warning(
                "Failed to start existing DifySandbox container `%s`: %s",
                container_name,
                (start_result.stderr or start_result.stdout).strip(),
            )
            return
        _LOCAL_DIFYSANDBOX_STARTED_BY_APP = True

    if not _wait_for_port(host, port, timeout_seconds=startup_timeout_seconds):
        logger.warning(
            "Local DifySandbox container `%s` did not become reachable on %s:%s",
            container_name,
            host,
            port,
        )
        return

    logger.info("Local DifySandbox ready at %s:%s (container=%s)", host, port, container_name)


def _stop_local_difysandbox_if_needed() -> None:
    if not _LOCAL_DIFYSANDBOX_STARTED_BY_APP:
        return
    if not _docker_available():
        return
    if not _LOCAL_DIFYSANDBOX_CONTAINER_NAME:
        return

    stop_result = _run_docker_command(["stop", _LOCAL_DIFYSANDBOX_CONTAINER_NAME])
    if stop_result.returncode == 0:
        logger.info("Stopped local DifySandbox container `%s`", _LOCAL_DIFYSANDBOX_CONTAINER_NAME)
    else:
        logger.warning(
            "Failed to stop local DifySandbox container `%s`: %s",
            _LOCAL_DIFYSANDBOX_CONTAINER_NAME,
            (stop_result.stderr or stop_result.stdout).strip(),
        )


def _ensure_local_artifact_worker_service_if_needed() -> None:
    global _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP, _LOCAL_ARTIFACT_WORKER_PROCESS

    if not _is_truthy(os.getenv("ARTIFACT_WORKER_AUTO_BOOTSTRAP", "1")):
        return
    if str(os.getenv("ARTIFACT_WORKER_CLIENT_MODE") or "").strip().lower() != "http":
        return

    base_url = (os.getenv("ARTIFACT_WORKER_BASE_URL") or "").strip()
    parsed = _parse_endpoint_host_port(base_url)
    if not parsed:
        logger.warning("Artifact worker base URL is invalid: %s", base_url)
        return
    host, port = parsed
    if not _is_local_host(host):
        return
    if _is_port_open(host, port):
        logger.info("Artifact worker service is already reachable at %s:%s", host, port)
        return

    backend_dir = Path(__file__).resolve().parents[3]
    log_path = Path(os.getenv("ARTIFACT_WORKER_LOG_PATH", "/tmp/talmudpedia-artifact-worker.log"))
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.artifact_worker.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    with log_path.open("ab") as log_file:
        _LOCAL_ARTIFACT_WORKER_PROCESS = subprocess.Popen(
            command,
            cwd=str(backend_dir),
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    startup_timeout_seconds = float((os.getenv("ARTIFACT_WORKER_STARTUP_TIMEOUT_SECONDS") or "20").strip())
    if _wait_for_port(host, port, timeout_seconds=startup_timeout_seconds):
        _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP = True
        logger.info("Started local artifact worker service at %s:%s", host, port)
    else:
        logger.warning("Artifact worker service did not become ready at %s:%s", host, port)


def _stop_local_artifact_worker_service_if_needed() -> None:
    global _LOCAL_ARTIFACT_WORKER_PROCESS, _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP
    if not _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP:
        return
    process = _LOCAL_ARTIFACT_WORKER_PROCESS
    if process is None or process.poll() is not None:
        _LOCAL_ARTIFACT_WORKER_PROCESS = None
        _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP = False
        return
    process.terminate()
    try:
        process.wait(timeout=8)
        logger.info("Stopped local artifact worker service")
    except Exception:
        process.kill()
        logger.warning("Force-killed local artifact worker service")
    _LOCAL_ARTIFACT_WORKER_PROCESS = None
    _LOCAL_ARTIFACT_WORKER_STARTED_BY_APP = False


def _is_truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _run_docker_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _parse_endpoint_host_port(endpoint: str) -> tuple[str, int] | None:
    parsed = urlparse((endpoint or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.hostname, int(parsed.port or default_port)


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, *, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.25)
    return _is_port_open(host, port)
