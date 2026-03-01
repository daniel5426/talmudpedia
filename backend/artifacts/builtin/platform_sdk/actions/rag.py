from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_pipelines(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.list_visual_pipelines(tenant_slug=payload.get("tenant_slug"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_pipelines_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_pipelines_failed", "detail": str(exc)}]


def create_or_update_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    tenant_slug = payload.get("tenant_slug")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if pipeline_id:
            skipped["pipeline_id"] = str(pipeline_id)
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if pipeline_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("pipeline_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.rag.update_visual_pipeline(
                str(pipeline_id),
                patch_payload,
                tenant_slug=tenant_slug,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.rag.create_visual_pipeline(
                payload,
                tenant_slug=tenant_slug,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_or_update_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_or_update_pipeline_failed", "detail": str(exc)}]


def compile_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.compile_visual_pipeline(
            str(pipeline_id),
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "compile_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "compile_pipeline_failed", "detail": str(exc)}]


def create_job(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    executable_pipeline_id = payload.get("executable_pipeline_id")
    tenant_slug = payload.get("tenant_slug")
    input_params = payload.get("input_params") if isinstance(payload.get("input_params"), dict) else {}

    missing: List[str] = []
    if not executable_pipeline_id:
        missing.append("executable_pipeline_id")
    if not tenant_slug:
        missing.append("tenant_slug")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "executable_pipeline_id": str(executable_pipeline_id),
            "request": {"input_params": input_params},
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.create_job(
            str(executable_pipeline_id),
            input_params,
            tenant_slug=str(tenant_slug),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_job_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_job_failed", "detail": str(exc)}]


def get_job(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    job_id = payload.get("job_id") or payload.get("id")
    if not job_id:
        return None, [{"error": "missing_fields", "fields": ["job_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_job(str(job_id), tenant_slug=payload.get("tenant_slug"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_job_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_job_failed", "detail": str(exc)}]


def get_step_data(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    job_id = payload.get("job_id")
    step_id = payload.get("step_id")
    data_type = payload.get("data_type") or payload.get("type")

    missing: List[str] = []
    if not job_id:
        missing.append("job_id")
    if not step_id:
        missing.append("step_id")
    if not data_type:
        missing.append("data_type")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_step_data(
            str(job_id),
            str(step_id),
            str(data_type),
            page=int(payload.get("page", 1) or 1),
            limit=int(payload.get("limit", 20) or 20),
            tenant_slug=payload.get("tenant_slug"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_step_data_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_step_data_failed", "detail": str(exc)}]
