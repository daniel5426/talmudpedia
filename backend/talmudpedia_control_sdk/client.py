from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable, Dict, Mapping, Optional

import requests

from .errors import ControlPlaneSDKError
from .types import RequestOptions, ResponseEnvelope

TokenProvider = Callable[[], Optional[str]]
TenantResolver = Callable[[], Optional[str]]


class ControlPlaneClient:
    def __init__(
        self,
        *,
        base_url: str,
        token_provider: Optional[TokenProvider] = None,
        token: Optional[str] = None,
        tenant_id: Optional[str] = None,
        tenant_resolver: Optional[TenantResolver] = None,
        timeout: float = 30.0,
        user_agent: str = "talmudpedia-control-sdk-python/1",
        default_request_metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[requests.sessions.Session] = None,
    ) -> None:
        if token_provider is not None and token is not None:
            raise ValueError("Provide either token_provider or token, not both.")
        if tenant_resolver is not None and tenant_id is not None:
            raise ValueError("Provide either tenant_resolver or tenant_id, not both.")
        self.base_url = base_url.rstrip("/")
        self._token_provider = token_provider or (lambda: token)
        self.tenant_id = str(tenant_id) if tenant_id is not None else None
        self._tenant_resolver = tenant_resolver
        self.timeout = timeout
        self.user_agent = user_agent
        self.default_request_metadata = dict(default_request_metadata or {})
        self.session = session or requests.Session()

        from .agents import AgentsAPI
        from .auth import AuthAPI
        from .artifacts import ArtifactsAPI
        from .catalog import CatalogAPI
        from .credentials import CredentialsAPI
        from .embedded_agents import EmbeddedAgentsAPI
        from .knowledge_stores import KnowledgeStoresAPI
        from .models import ModelsAPI
        from .orchestration import OrchestrationAPI
        from .rag import RagAPI
        from .tools import ToolsAPI
        from .workload_security import WorkloadSecurityAPI

        self.catalog = CatalogAPI(self)
        self.agents = AgentsAPI(self)
        self.tools = ToolsAPI(self)
        self.artifacts = ArtifactsAPI(self)
        self.rag = RagAPI(self)
        self.models = ModelsAPI(self)
        self.credentials = CredentialsAPI(self)
        self.embedded_agents = EmbeddedAgentsAPI(self)
        self.knowledge_stores = KnowledgeStoresAPI(self)
        self.workload_security = WorkloadSecurityAPI(self)
        self.auth = AuthAPI(self)
        self.orchestration = OrchestrationAPI(self)

    @classmethod
    def from_env(
        cls,
        *,
        base_url_env: str = "TEST_BASE_URL",
        token_env: str = "TEST_API_KEY",
        tenant_env: str = "TEST_TENANT_ID",
        timeout: float = 30.0,
        user_agent: str = "talmudpedia-control-sdk-python/1",
        default_request_metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[requests.sessions.Session] = None,
    ) -> "ControlPlaneClient":
        base_url = os.getenv(base_url_env) or "http://localhost:8000"
        token = os.getenv(token_env)
        tenant_id = os.getenv(tenant_env)
        return cls(
            base_url=base_url,
            token=token,
            tenant_id=tenant_id,
            timeout=timeout,
            user_agent=user_agent,
            default_request_metadata=default_request_metadata,
            session=session,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Any] = None,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        options: Optional[RequestOptions] = None,
        mutation: bool = False,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> ResponseEnvelope:
        response = self.request_raw(
            method,
            path,
            params=params,
            json_body=json_body,
            data=data,
            files=files,
            options=options,
            mutation=mutation,
            headers=headers,
            timeout=timeout,
        )
        return self._normalize_response(response)

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Any] = None,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        options: Optional[RequestOptions] = None,
        mutation: bool = False,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        request_options: RequestOptions = dict(options or {})
        request_headers = self._build_headers(
            mutation=mutation,
            options=request_options,
            headers=headers,
        )
        merged_params = self._build_query_params(params=params, options=request_options)
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method.upper(),
            url=url,
            params=merged_params,
            json=json_body,
            data=data,
            files=files,
            headers=request_headers,
            timeout=timeout or self.timeout,
        )
        if response.status_code >= 400:
            raise self._build_error(response)
        return response

    def _build_headers(
        self,
        *,
        mutation: bool,
        options: RequestOptions,
        headers: Optional[Mapping[str, str]],
    ) -> Dict[str, str]:
        request_id = str(uuid.uuid4())
        base_headers: Dict[str, str] = {
            "X-SDK-Contract": "1",
            "User-Agent": self.user_agent,
            "X-Request-ID": request_id,
        }
        tenant_id = self._resolve_tenant_id()
        if tenant_id:
            base_headers["X-Tenant-ID"] = tenant_id
        token = self._resolve_token()
        if token:
            base_headers["Authorization"] = f"Bearer {token}"

        metadata = dict(self.default_request_metadata)
        metadata.update(dict(options.get("request_metadata") or {}))
        if metadata:
            base_headers["X-Request-Metadata"] = json.dumps(metadata, separators=(",", ":"))

        if mutation:
            idempotency_key = options.get("idempotency_key")
            if not idempotency_key:
                idempotency_key = str(uuid.uuid4())
            base_headers["X-Idempotency-Key"] = str(idempotency_key)

        if headers:
            base_headers.update({k: str(v) for k, v in headers.items()})
        return base_headers

    def _build_query_params(
        self,
        *,
        params: Optional[Mapping[str, Any]],
        options: RequestOptions,
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if params:
            merged.update(dict(params))
        if "dry_run" in options:
            merged["dry_run"] = bool(options["dry_run"])
        if "validate_only" in options:
            merged["validate_only"] = bool(options["validate_only"])
        return merged

    def _resolve_token(self) -> Optional[str]:
        try:
            token = self._token_provider() if self._token_provider else None
        except Exception as exc:
            raise ControlPlaneSDKError(
                code="TOKEN_PROVIDER_ERROR",
                message=f"Token provider failed: {exc}",
                retryable=False,
            ) from exc
        if token is None:
            return None
        token_text = str(token).strip()
        return token_text or None

    def _resolve_tenant_id(self) -> Optional[str]:
        if self._tenant_resolver is not None:
            try:
                tenant_id = self._tenant_resolver()
            except Exception as exc:
                raise ControlPlaneSDKError(
                    code="TENANT_RESOLVER_ERROR",
                    message=f"Tenant resolver failed: {exc}",
                    retryable=False,
                ) from exc
            if tenant_id is None:
                return None
            tenant_text = str(tenant_id).strip()
            return tenant_text or None

        if self.tenant_id is None:
            return None
        tenant_text = str(self.tenant_id).strip()
        return tenant_text or None

    def _normalize_response(self, response: requests.Response) -> ResponseEnvelope:
        payload: Any
        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text}

        if isinstance(payload, dict) and {"data", "meta", "errors"}.issubset(payload.keys()):
            return payload

        envelope: ResponseEnvelope = {
            "data": payload,
            "meta": {
                "request_id": response.headers.get("X-Request-ID", ""),
                "trace_id": response.headers.get("X-Trace-ID", ""),
                "idempotency_reused": response.headers.get("X-Idempotency-Reused") == "true",
                "warnings": [],
            },
            "errors": [],
        }
        return envelope

    def _build_error(self, response: requests.Response) -> ControlPlaneSDKError:
        message = response.text
        code = "UPSTREAM_ERROR" if response.status_code >= 500 else "INVALID_ARGUMENT"
        retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
        details: Dict[str, Any] = {}
        request_id = str(response.headers.get("X-Request-ID") or "").strip()
        trace_id = str(response.headers.get("X-Trace-ID") or "").strip()
        try:
            body = response.json()
            if isinstance(body, dict):
                details = body
                if body.get("code"):
                    code = str(body["code"])
                if body.get("message"):
                    message = str(body["message"])
                detail = body.get("detail")
                if isinstance(detail, dict):
                    details = detail
                    if detail.get("code"):
                        code = str(detail["code"])
                    if detail.get("message"):
                        message = str(detail["message"])
                    else:
                        message = str(detail)
                elif detail:
                    message = str(detail)
                if body.get("retryable") is not None:
                    retryable = bool(body.get("retryable"))
        except Exception:
            pass
        if request_id and "request_id" not in details:
            details["request_id"] = request_id
        if trace_id and "trace_id" not in details:
            details["trace_id"] = trace_id
        return ControlPlaneSDKError(
            code=code,
            message=message,
            http_status=response.status_code,
            retryable=retryable,
            details=details or None,
        )
