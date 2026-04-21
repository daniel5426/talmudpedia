from __future__ import annotations

from typing import Any, BinaryIO, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


def _organization_params(organization_id: Optional[str]) -> Dict[str, Any]:
    if not organization_id:
        return {}
    return {"organization_id": organization_id}


class RagAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get_operator_catalog(self, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request("GET", "/admin/pipelines/catalog", params=_organization_params(organization_id))

    def get_operator_schemas(
        self,
        operator_ids: list[str],
        organization_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/pipelines/operators/schema",
            params=_organization_params(organization_id),
            json_body={"operator_ids": list(operator_ids or [])},
        )

    def list_visual_pipelines(
        self,
        organization_id: Optional[str] = None,
        *,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        params = _organization_params(organization_id)
        params.update({"skip": skip, "limit": limit, "view": view})
        return self._client.request("GET", "/admin/pipelines/visual-pipelines", params=params)

    def create_visual_pipeline(
        self,
        spec: Dict[str, Any],
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/pipelines/visual-pipelines",
            params=_organization_params(organization_id),
            json_body=spec,
            options=options,
            mutation=True,
        )

    def get_visual_pipeline(self, pipeline_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}",
            params=_organization_params(organization_id),
        )

    def get_pipeline_graph(self, pipeline_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph",
            params=_organization_params(organization_id),
        )

    def update_visual_pipeline(
        self,
        pipeline_id: str,
        patch: Dict[str, Any],
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}",
            params=_organization_params(organization_id),
            json_body=patch,
            options=options,
            mutation=True,
        )

    def validate_graph_patch(
        self,
        pipeline_id: str,
        operations: list[Dict[str, Any]],
        organization_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph/validate-patch",
            params=_organization_params(organization_id),
            json_body={"operations": list(operations or [])},
        )

    def apply_graph_patch(
        self,
        pipeline_id: str,
        operations: list[Dict[str, Any]],
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph/apply-patch",
            params=_organization_params(organization_id),
            json_body={"operations": list(operations or [])},
            options=options,
            mutation=True,
        )

    def attach_knowledge_store_to_node(
        self,
        pipeline_id: str,
        *,
        node_id: str,
        knowledge_store_id: str,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph/attach-knowledge-store-to-node",
            params=_organization_params(organization_id),
            json_body={"node_id": node_id, "knowledge_store_id": knowledge_store_id},
            options=options,
            mutation=True,
        )

    def set_pipeline_node_config(
        self,
        pipeline_id: str,
        *,
        node_id: str,
        path: str,
        value: Any,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/graph/set-node-config",
            params=_organization_params(organization_id),
            json_body={"node_id": node_id, "path": path, "value": value},
            options=options,
            mutation=True,
        )

    def delete_visual_pipeline(
        self,
        pipeline_id: str,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}",
            params=_organization_params(organization_id),
            options=options,
            mutation=True,
        )

    def compile_visual_pipeline(
        self,
        pipeline_id: str,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/compile",
            params=_organization_params(organization_id),
            json_body={},
            options=options,
            mutation=True,
        )

    def list_pipeline_versions(self, pipeline_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/visual-pipelines/{pipeline_id}/versions",
            params=_organization_params(organization_id),
        )

    def get_executable_pipeline(self, exec_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/executable-pipelines/{exec_id}",
            params=_organization_params(organization_id),
        )

    def get_executable_input_schema(self, exec_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/executable-pipelines/{exec_id}/input-schema",
            params=_organization_params(organization_id),
        )

    def upload_input_file(
        self,
        file_name: str,
        file_obj: BinaryIO,
        organization_id: str,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/pipelines/pipeline-inputs/upload",
            params={"organization_id": organization_id},
            files={"file": (file_name, file_obj)},
        )

    def create_job(
        self,
        executable_pipeline_id: str,
        input_params: Dict[str, Any],
        organization_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        payload = {
            "executable_pipeline_id": executable_pipeline_id,
            "input_params": input_params or {},
        }
        return self._client.request(
            "POST",
            "/admin/pipelines/jobs",
            params={"organization_id": organization_id},
            json_body=payload,
            options=options,
            mutation=True,
        )

    def list_jobs(
        self,
        *,
        executable_pipeline_id: Optional[str] = None,
        visual_pipeline_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        organization_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if executable_pipeline_id:
            params["executable_pipeline_id"] = executable_pipeline_id
        if visual_pipeline_id:
            params["visual_pipeline_id"] = visual_pipeline_id
        if status:
            params["status"] = status
        if organization_id:
            params["organization_id"] = organization_id
        return self._client.request("GET", "/admin/pipelines/jobs", params=params)

    def get_job(self, job_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/pipelines/jobs/{job_id}",
            params=_organization_params(organization_id),
        )

    def list_job_steps(self, job_id: str, lite: bool = True, organization_id: Optional[str] = None) -> ResponseEnvelope:
        params: Dict[str, Any] = {"lite": lite}
        if organization_id:
            params["organization_id"] = organization_id
        return self._client.request("GET", f"/admin/pipelines/jobs/{job_id}/steps", params=params)

    def get_step_data(
        self,
        job_id: str,
        step_id: str,
        data_type: str,
        page: int = 1,
        limit: int = 20,
        organization_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {
            "type": data_type,
            "page": page,
            "limit": limit,
        }
        if organization_id:
            params["organization_id"] = organization_id
        return self._client.request(
            "GET",
            f"/admin/pipelines/jobs/{job_id}/steps/{step_id}/data",
            params=params,
        )

    def get_step_field(
        self,
        job_id: str,
        step_id: str,
        data_type: str,
        path: str,
        offset: int = 0,
        limit: int = 100000,
        organization_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {
            "type": data_type,
            "path": path,
            "offset": offset,
            "limit": limit,
        }
        if organization_id:
            params["organization_id"] = organization_id
        return self._client.request(
            "GET",
            f"/admin/pipelines/jobs/{job_id}/steps/{step_id}/field",
            params=params,
        )
