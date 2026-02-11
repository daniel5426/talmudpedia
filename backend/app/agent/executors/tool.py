from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from collections.abc import Mapping
from typing import Any
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import ProgrammingError

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.executors.retrieval_runtime import RetrievalPipelineRuntime
from app.db.postgres.models.registry import ToolRegistry
from app.services.credentials_service import CredentialsService
from app.services.mcp_client import call_mcp_tool
from app.services.tool_function_registry import get_tool_function, run_tool_function
from app.services.web_search import create_web_search_provider

logger = logging.getLogger(__name__)


class ToolNodeExecutor(BaseNodeExecutor):
    async def _mint_workload_token(
        self,
        grant_id: str | None,
        scope_subset: list[str] | None = None,
        audience: str = "talmudpedia-internal-api",
    ) -> str | None:
        if not grant_id:
            return None
        from app.db.postgres.engine import sessionmaker as async_sessionmaker
        from app.services.token_broker_service import TokenBrokerService

        async with async_sessionmaker() as token_db:
            broker = TokenBrokerService(token_db)
            token, _payload = await broker.mint_workload_token(
                grant_id=UUID(str(grant_id)),
                audience=audience,
                scope_subset=scope_subset,
            )
            await token_db.commit()
            return token

    async def _execute_http_tool(
        self,
        _tool: Any,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
        node_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = implementation_config.get("url") or input_data.get("url")
        if not url:
            raise ValueError("HTTP tool requires a URL")

        method = str(implementation_config.get("method") or input_data.get("method") or "POST").upper()
        headers = dict(implementation_config.get("headers", {}) or {})
        request_headers = input_data.get("headers")
        if isinstance(request_headers, dict):
            headers.update(request_headers)

        grant_id = (node_context or {}).get("grant_id")
        scope_subset = implementation_config.get("scope_subset")
        if implementation_config.get("use_workload_token") and not grant_id:
            raise PermissionError("Tool requires workload token, but no delegation grant is available")
        if grant_id and implementation_config.get("use_workload_token"):
            workload_token = await self._mint_workload_token(
                grant_id=str(grant_id),
                scope_subset=scope_subset if isinstance(scope_subset, list) else None,
                audience=implementation_config.get("audience", "talmudpedia-internal-api"),
            )
            if workload_token:
                headers["Authorization"] = f"Bearer {workload_token}"

        timeout_s = implementation_config.get("timeout_s")
        timeout = httpx.Timeout(timeout_s) if timeout_s else None
        body = input_data.get("body")
        params = input_data.get("params") if isinstance(input_data.get("params"), dict) else None
        if body is None:
            body = {k: v for k, v in input_data.items() if k not in {"url", "method", "headers", "params"}}

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                json=body if method not in {"GET", "DELETE"} else None,
                params=params if method in {"GET", "DELETE"} else params,
                headers=headers,
            )
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        payload: Any
        if "application/json" in content_type:
            payload = response.json()
        else:
            payload = response.text
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": payload,
        }

    async def _execute_function_tool(
        self,
        _tool: Any,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        function_name = implementation_config.get("function_name")
        if not function_name:
            raise ValueError("Function tool is missing function_name in implementation_config")

        fn = get_tool_function(function_name)
        if not fn:
            raise RuntimeError(f"Function tool '{function_name}' is not registered")

        payload = input_data.get("args") if isinstance(input_data.get("args"), dict) else input_data
        result = await run_tool_function(fn, payload)
        if isinstance(result, dict):
            return result
        return {"result": result}

    async def _execute_mcp_tool(
        self,
        _tool: Any,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
        timeout_s: int | None,
    ) -> dict[str, Any]:
        server_url = implementation_config.get("server_url")
        tool_name = implementation_config.get("tool_name")
        headers = implementation_config.get("headers")
        arguments = input_data.get("arguments") if isinstance(input_data.get("arguments"), dict) else input_data
        return await call_mcp_tool(
            server_url=server_url,
            tool_name=tool_name,
            arguments=arguments,
            headers=headers,
            timeout_s=timeout_s,
        )

    async def _execute_retrieval_pipeline_tool(
        self,
        _tool: Any,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.tenant_id:
            raise PermissionError("Retrieval pipeline tools require tenant context")

        pipeline_id_raw = implementation_config.get("pipeline_id") or input_data.get("pipeline_id")
        if not pipeline_id_raw:
            raise ValueError("retrieval pipeline tool requires pipeline_id")

        nested_input = input_data.get("input") if isinstance(input_data.get("input"), dict) else {}
        query = (
            input_data.get("query")
            or input_data.get("q")
            or input_data.get("search_query")
            or input_data.get("keywords")
            or input_data.get("text")
            or input_data.get("value")
            or nested_input.get("query")
            or nested_input.get("q")
            or nested_input.get("search_query")
            or nested_input.get("keywords")
            or nested_input.get("text")
            or nested_input.get("value")
        )
        if not query:
            raise ValueError("retrieval pipeline tool requires a query")

        top_k = int(input_data.get("top_k") or implementation_config.get("top_k") or 10)
        filters = input_data.get("filters") if isinstance(input_data.get("filters"), dict) else None

        runtime = RetrievalPipelineRuntime(self.db, self.tenant_id)
        results, _job = await runtime.run_query(
            pipeline_id=UUID(str(pipeline_id_raw)),
            query=str(query),
            top_k=top_k,
            filters=filters,
        )
        return {
            "query": str(query),
            "pipeline_id": str(pipeline_id_raw),
            "results": results,
            "count": len(results),
        }

    async def _execute_web_fetch_builtin(
        self,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        url = str(input_data.get("url") or implementation_config.get("url") or "").strip()
        if not url:
            raise ValueError("web_fetch requires url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("web_fetch supports only http/https URLs")

        method = str(input_data.get("method") or implementation_config.get("method") or "GET").upper()
        headers = dict(implementation_config.get("headers", {}) or {})
        if isinstance(input_data.get("headers"), dict):
            headers.update(input_data["headers"])

        timeout_s = int(implementation_config.get("timeout_s") or 15)
        max_bytes = int(implementation_config.get("max_bytes") or 250_000)
        body = input_data.get("body")

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), follow_redirects=True) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=body if method not in {"GET", "DELETE"} else None,
            )
            response.raise_for_status()

        raw_bytes = response.content or b""
        truncated = len(raw_bytes) > max_bytes
        raw_bytes = raw_bytes[:max_bytes]
        encoding = response.encoding or "utf-8"
        text_body = raw_bytes.decode(encoding, errors="replace")

        output: dict[str, Any] = {
            "url": str(response.url),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "text": text_body,
            "truncated": truncated,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if "application/json" in output["content_type"]:
            try:
                output["json"] = json.loads(text_body)
            except Exception:
                pass
        return output

    async def _execute_web_search_builtin(
        self,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        nested_input = input_data.get("input") if isinstance(input_data.get("input"), dict) else {}
        query = str(
            input_data.get("query")
            or input_data.get("q")
            or input_data.get("search_query")
            or input_data.get("keywords")
            or input_data.get("text")
            or input_data.get("value")
            or nested_input.get("query")
            or nested_input.get("q")
            or nested_input.get("search_query")
            or nested_input.get("keywords")
            or nested_input.get("text")
            or nested_input.get("value")
            or ""
        ).strip()
        if not query:
            raise ValueError("web_search requires query (supported aliases: query, q, search_query, keywords, text, value)")

        provider_name = str(implementation_config.get("provider") or "serper").strip().lower()
        top_k = int(input_data.get("top_k") or implementation_config.get("top_k") or 5)
        timeout_s = int(implementation_config.get("timeout_s") or 15)

        api_key = implementation_config.get("api_key")
        endpoint = implementation_config.get("endpoint")

        cred_ref = implementation_config.get("credentials_ref")
        if not api_key and cred_ref and self.tenant_id:
            credentials_service = CredentialsService(self.db, self.tenant_id)
            credential = await credentials_service.get_by_id(UUID(str(cred_ref)))
            if credential is None:
                raise ValueError("web_search credential_ref not found")
            if not credential.is_enabled:
                raise ValueError("web_search credential_ref is disabled")
            payload = credential.credentials or {}
            api_key = payload.get("api_key") or payload.get("token")
            endpoint = endpoint or payload.get("endpoint")

        if not api_key and provider_name == "serper":
            import os

            api_key = os.getenv("SERPER_API_KEY")

        if not api_key:
            raise ValueError("web_search provider credentials are missing")

        provider = create_web_search_provider(
            provider_name,
            api_key=str(api_key),
            endpoint=str(endpoint) if endpoint else None,
            timeout_s=timeout_s,
        )
        return await provider.search(query=query, top_k=top_k)

    def _json_lookup(self, payload: Any, path: str) -> Any:
        if not path:
            return None
        cursor = payload
        for token in str(path).split("."):
            if isinstance(cursor, dict):
                cursor = cursor.get(token)
            else:
                return None
        return cursor

    async def _execute_json_transform_builtin(
        self,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        data = input_data.get("data") if "data" in input_data else input_data
        pick = input_data.get("pick")
        if pick is None:
            pick = implementation_config.get("pick")
        mapping = input_data.get("mapping")
        if mapping is None:
            mapping = implementation_config.get("mapping")
        defaults = input_data.get("defaults")
        if defaults is None:
            defaults = implementation_config.get("defaults")

        if isinstance(mapping, dict) and mapping:
            result = {out_key: self._json_lookup(data, src_path) for out_key, src_path in mapping.items()}
        elif isinstance(pick, list) and pick:
            result = {key: self._json_lookup(data, str(key)) for key in pick}
        else:
            result = data

        if isinstance(defaults, dict):
            if not isinstance(result, dict):
                result = {"result": result}
            for key, value in defaults.items():
                if key not in result or result[key] is None:
                    result[key] = value

        return {"result": result}

    def _parse_datetime(self, value: str) -> datetime:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    async def _execute_datetime_utils_builtin(
        self,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
    ) -> dict[str, Any]:
        operation = str(input_data.get("operation") or implementation_config.get("operation") or "now_utc")
        tz_name = str(input_data.get("timezone") or implementation_config.get("timezone") or "UTC")

        if operation == "now_utc":
            result: Any = datetime.now(timezone.utc).isoformat()
        elif operation == "now_local":
            result = datetime.now(timezone.utc).astimezone(ZoneInfo(tz_name)).isoformat()
        elif operation == "format":
            value = input_data.get("value") or implementation_config.get("value")
            if not value:
                raise ValueError("datetime_utils format requires value")
            dt = self._parse_datetime(str(value)).astimezone(ZoneInfo(tz_name))
            fmt = str(input_data.get("format") or implementation_config.get("format") or "%Y-%m-%d %H:%M:%S")
            result = dt.strftime(fmt)
        elif operation == "add":
            value = input_data.get("value") or implementation_config.get("value") or datetime.now(timezone.utc).isoformat()
            dt = self._parse_datetime(str(value))
            amount = int(input_data.get("amount") or implementation_config.get("amount") or 0)
            unit = str(input_data.get("unit") or implementation_config.get("unit") or "seconds").lower()
            delta_map = {
                "seconds": timedelta(seconds=amount),
                "minutes": timedelta(minutes=amount),
                "hours": timedelta(hours=amount),
                "days": timedelta(days=amount),
            }
            if unit not in delta_map:
                raise ValueError("datetime_utils add supports units: seconds, minutes, hours, days")
            result = (dt + delta_map[unit]).isoformat()
        elif operation == "diff":
            value = input_data.get("value") or implementation_config.get("value")
            other = input_data.get("other") or implementation_config.get("other")
            if not value or not other:
                raise ValueError("datetime_utils diff requires value and other")
            dt_a = self._parse_datetime(str(value))
            dt_b = self._parse_datetime(str(other))
            diff_seconds = (dt_a - dt_b).total_seconds()
            unit = str(input_data.get("unit") or implementation_config.get("unit") or "seconds").lower()
            if unit == "minutes":
                result = diff_seconds / 60
            elif unit == "hours":
                result = diff_seconds / 3600
            elif unit == "days":
                result = diff_seconds / 86400
            else:
                result = diff_seconds
        else:
            raise ValueError(f"Unsupported datetime_utils operation: {operation}")

        return {"operation": operation, "result": result}

    async def _execute_builtin_dispatch(
        self,
        *,
        tool: Any,
        input_data: dict[str, Any],
        implementation_config: dict[str, Any],
        execution_config: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        builtin_key = str(getattr(tool, "builtin_key", "") or "").strip().lower()
        if not builtin_key:
            builtin_key = str(implementation_config.get("builtin") or "").strip().lower()

        if not builtin_key:
            return None

        if builtin_key == "retrieval_pipeline":
            return await self._execute_retrieval_pipeline_tool(tool, input_data, implementation_config)
        if builtin_key == "http_request":
            return await self._execute_http_tool(tool, input_data, implementation_config, context)
        if builtin_key == "function_call":
            return await self._execute_function_tool(tool, input_data, implementation_config)
        if builtin_key == "mcp_call":
            timeout_s = execution_config.get("timeout_s") if isinstance(execution_config, dict) else None
            return await self._execute_mcp_tool(tool, input_data, implementation_config, timeout_s)
        if builtin_key == "web_fetch":
            return await self._execute_web_fetch_builtin(input_data, implementation_config)
        if builtin_key == "web_search":
            return await self._execute_web_search_builtin(input_data, implementation_config)
        if builtin_key == "json_transform":
            return await self._execute_json_transform_builtin(input_data, implementation_config)
        if builtin_key == "datetime_utils":
            return await self._execute_datetime_utils_builtin(input_data, implementation_config)

        raise NotImplementedError(f"Unsupported built-in tool key: {builtin_key}")

    def _resolve_input_data(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        prefer_last = False
        if isinstance(config, dict):
            if config.get("input_source") == "last_agent_output":
                prefer_last = True
            if config.get("prefer_last_agent_output") is True:
                prefer_last = True

        last_output = (state.get("state") or {}).get("last_agent_output")
        if isinstance(last_output, Mapping) and not isinstance(last_output, dict):
            last_output = dict(last_output)
        if prefer_last and isinstance(last_output, dict) and last_output:
            return last_output

        parsed_message = self._try_parse_last_message_json(state)
        if isinstance(parsed_message, dict) and parsed_message.get("action"):
            return parsed_message

        node_output = self._try_extract_last_agent_output(state)
        if isinstance(node_output, dict) and node_output.get("action"):
            return node_output

        input_data = state.get("context")
        if isinstance(input_data, Mapping) and not isinstance(input_data, dict):
            input_data = dict(input_data)
        if isinstance(input_data, dict) and input_data:
            if isinstance(last_output, dict) and last_output and input_data.get("action") == "fetch_catalog":
                return last_output
            if input_data.get("action") == "fetch_catalog":
                parsed = self._try_parse_last_message_json(state)
                if parsed:
                    return parsed
        if not isinstance(input_data, dict) or not input_data:
            input_data = last_output

        if not isinstance(input_data, dict) or not input_data:
            last_msg = state.get("messages", [])[-1] if state.get("messages") else None
            if last_msg:
                if isinstance(last_msg, dict):
                    input_data = {"text": last_msg.get("content")}
                else:
                    input_data = {"text": getattr(last_msg, "content", str(last_msg))}

        if not isinstance(input_data, dict):
            input_data = {}

        return input_data

    def _try_extract_last_agent_output(self, state: dict[str, Any]) -> dict[str, Any]:
        node_outputs = state.get("_node_outputs") or {}
        if isinstance(node_outputs, Mapping):
            for output in node_outputs.values():
                if isinstance(output, Mapping):
                    output = dict(output)
                    nested_state = output.get("state")
                    if isinstance(nested_state, Mapping):
                        nested_state = dict(nested_state)
                    if isinstance(nested_state, dict) and "last_agent_output" in nested_state:
                        last = nested_state.get("last_agent_output")
                        if isinstance(last, Mapping) and not isinstance(last, dict):
                            last = dict(last)
                        if isinstance(last, dict):
                            return last
        return {}

    def _try_parse_last_message_json(self, state: dict[str, Any]) -> dict[str, Any]:
        last_msg = state.get("messages", [])[-1] if state.get("messages") else None
        if not last_msg:
            return {}
        content = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", None)
        if not isinstance(content, str):
            return {}
        text = content.strip()
        if not (text.startswith("{") and text.endswith("}")):
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            logger.error(f"Failed to parse last message JSON: {text}")
        return {}

    def _build_literal_input_mappings(self, input_data: Any) -> dict[str, Any]:
        if isinstance(input_data, Mapping):
            if not isinstance(input_data, dict):
                return dict(input_data)
            return input_data
        return {"payload": input_data}

    def _sanitize_input_data(self, input_data: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(input_data or {})
        for key in ("token", "bearer_token", "api_key", "authorization", "auth_token"):
            sanitized.pop(key, None)
        return sanitized

    def _is_production_mode(self, context: dict[str, Any] | None) -> bool:
        if not isinstance(context, dict):
            return False
        mode = context.get("mode")
        if not mode:
            langgraph_config = context.get("langgraph_config")
            if isinstance(langgraph_config, dict):
                configurable = langgraph_config.get("configurable")
                if isinstance(configurable, dict):
                    mode = configurable.get("mode")
        return str(mode or "debug").strip().lower() == "production"

    def _status_text(self, tool: Any) -> str:
        status = getattr(tool, "status", None)
        return str(getattr(status, "value", status or "")).lower()

    def _assert_runtime_policy(self, tool: Any, context: dict[str, Any] | None) -> None:
        if not getattr(tool, "is_active", False):
            raise PermissionError(f"Tool {getattr(tool, 'id', '')} is inactive")
        if self._is_production_mode(context):
            if self._status_text(tool) != "published":
                raise PermissionError("Tool must be published for production execution")

    async def _has_artifact_columns(self) -> bool:
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'tool_registry'
                      AND column_name IN ('artifact_id', 'artifact_version')
                    """
                )
            )
            cols = {row[0] for row in result.all()}
            return "artifact_id" in cols and "artifact_version" in cols
        except Exception:
            try:
                result = await self.db.execute(text("PRAGMA table_info(tool_registry)"))
                cols = {row[1] for row in result.all()}
                return "artifact_id" in cols and "artifact_version" in cols
            except Exception:
                return False

    async def _load_tool(self, tool_id: UUID) -> Any:
        tool = None
        try:
            if await self._has_artifact_columns():
                scope_condition = ToolRegistry.tenant_id == None if self.tenant_id is None else or_(
                    ToolRegistry.tenant_id == self.tenant_id,
                    ToolRegistry.tenant_id == None,
                )
                result = await self.db.execute(
                    select(ToolRegistry).where(
                        and_(
                            ToolRegistry.id == tool_id,
                            scope_condition,
                        )
                    )
                )
                tool = result.scalar_one_or_none()
            else:
                raise ProgrammingError("tool_registry missing artifact columns", None, None)
        except ProgrammingError:
            try:
                await self.db.rollback()
            except Exception:
                pass

            if self.tenant_id is None:
                raw_query = """
                    SELECT id, name, description, scope, schema, config_schema, is_active, is_system
                    FROM tool_registry
                    WHERE id = :tool_id AND tenant_id IS NULL
                """
                raw_params = {"tool_id": str(tool_id)}
            else:
                raw_query = """
                    SELECT id, name, description, scope, schema, config_schema, is_active, is_system
                    FROM tool_registry
                    WHERE id = :tool_id AND (tenant_id = :tenant_id OR tenant_id IS NULL)
                """
                raw_params = {"tool_id": str(tool_id), "tenant_id": str(self.tenant_id)}

            row = (await self.db.execute(text(raw_query), raw_params)).first()
            if row:
                tool = SimpleNamespace(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    scope=row[3],
                    schema=row[4] or {},
                    config_schema=row[5] or {},
                    is_active=row[6],
                    is_system=row[7],
                    artifact_id=None,
                    artifact_version=None,
                    builtin_key=None,
                    is_builtin_template=False,
                    status="published" if row[6] else "disabled",
                )

        if not tool:
            raise ValueError(f"Tool {tool_id} not found")
        return tool

    async def validate_config(self, config: dict[str, Any]) -> ValidationResult:
        if not config.get("tool_id"):
            return ValidationResult(valid=False, errors=["Missing 'tool_id' in configuration"])
        return ValidationResult(valid=True)

    async def execute(self, state: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        tool_id_str = config.get("tool_id")
        if not tool_id_str:
            raise ValueError("Missing tool_id")

        tool_id = UUID(tool_id_str)
        tool = await self._load_tool(tool_id)
        self._assert_runtime_policy(tool, context)

        input_data = self._sanitize_input_data(self._resolve_input_data(state, config))

        from app.agent.execution.emitter import active_emitter

        emitter = active_emitter.get()
        node_id = context.get("node_id", "tool_node") if context else "tool_node"
        if emitter:
            emitter.emit_tool_start(tool.name, input_data, node_id)

        config_schema = tool.config_schema or {}
        if isinstance(config_schema, str):
            try:
                config_schema = json.loads(config_schema)
            except Exception:
                config_schema = {}

        implementation_config = config_schema.get("implementation", {}) if isinstance(config_schema, dict) else {}
        execution_config = config_schema.get("execution", {}) if isinstance(config_schema, dict) else {}
        timeout_s = execution_config.get("timeout_s") if isinstance(execution_config, dict) else None

        impl_type = getattr(tool, "implementation_type", None) or implementation_config.get("type", "internal")
        if hasattr(impl_type, "value"):
            impl_type = impl_type.value
        impl_type = str(impl_type).lower()

        try:
            if getattr(tool, "artifact_id", None):
                from app.agent.executors.artifact import ArtifactNodeExecutor

                artifact_executor = ArtifactNodeExecutor(self.tenant_id, self.db)
                artifact_config = {
                    **config,
                    "_artifact_id": tool.artifact_id,
                    "_artifact_version": getattr(tool, "artifact_version", None),
                    "label": tool.name,
                    "input_mappings": self._build_literal_input_mappings(input_data),
                    "_strict_validation": True,
                    "_literal_inputs": True,
                }
                result = await artifact_executor.execute(state, artifact_config, context)
                if emitter:
                    emitter.emit_tool_end(tool.name, result, node_id)
                return result

            if impl_type == "artifact" and implementation_config.get("artifact_id"):
                from app.agent.executors.artifact import ArtifactNodeExecutor

                artifact_executor = ArtifactNodeExecutor(self.tenant_id, self.db)
                artifact_config = {
                    **config,
                    "_artifact_id": implementation_config.get("artifact_id"),
                    "_artifact_version": implementation_config.get("artifact_version"),
                    "label": tool.name,
                    "input_mappings": self._build_literal_input_mappings(input_data),
                    "_strict_validation": True,
                    "_literal_inputs": True,
                }
                result = await artifact_executor.execute(state, artifact_config, context)
                if emitter:
                    emitter.emit_tool_end(tool.name, result, node_id)
                return result

            output_data = await self._execute_builtin_dispatch(
                tool=tool,
                input_data=input_data,
                implementation_config=implementation_config,
                execution_config=execution_config,
                context=context,
            )
            if output_data is None:
                if impl_type == "http":
                    output_data = await self._execute_http_tool(tool, input_data, implementation_config, context)
                elif impl_type == "function":
                    output_data = await self._execute_function_tool(tool, input_data, implementation_config)
                elif impl_type == "mcp":
                    output_data = await self._execute_mcp_tool(tool, input_data, implementation_config, timeout_s)
                elif impl_type == "rag_retrieval":
                    output_data = await self._execute_retrieval_pipeline_tool(tool, input_data, implementation_config)
                else:
                    raise NotImplementedError(f"Unsupported tool implementation type: {impl_type}")

            if emitter:
                emitter.emit_tool_end(tool.name, output_data, node_id)

            return {
                "tool_outputs": [output_data],
                "context": output_data,
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise e
