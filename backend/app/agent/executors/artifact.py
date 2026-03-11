"""
ArtifactNodeExecutor - Executes artifact-based agent nodes.

This executor dynamically loads and runs artifact handlers for agent nodes,
providing full tracing, error handling, and state management.
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.db.postgres.models.artifact_runtime import ArtifactKind, ArtifactRunDomain, ArtifactRunStatus
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService

logger = logging.getLogger(__name__)


def _input_specs_from_schema(schema: Dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = set(schema.get("required") or [])
    specs = []
    for name, value in properties.items():
        if not isinstance(value, dict):
            value = {}
        specs.append(
            {
                "name": name,
                "type": value.get("type", "any"),
                "required": name in required,
                "default": value.get("default"),
                "description": value.get("description"),
            }
        )
    return specs


class ArtifactNodeExecutor(BaseNodeExecutor):
    """
    Generic executor for artifact-based agent nodes.
    
    This executor loads the artifact's handler.py and calls its execute() function.
    It supports both sync and async handlers, providing full tracing integration.
    
    Handler contract:
        The handler.py must define:
            def execute(state: dict, config: dict, context: dict) -> dict
        or:
            async def execute(state: dict, config: dict, context: dict) -> dict
    """
    
    @staticmethod
    def _parse_uuid(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        try:
            return UUID(str(value))
        except Exception:
            return None

    @staticmethod
    def _is_production_mode(context: Optional[Dict[str, Any]]) -> bool:
        return str((context or {}).get("mode") or "debug").strip().lower() == "production"

    async def _resolve_tenant_revision(
        self,
        *,
        artifact_id: UUID,
        pinned_revision_id: UUID | None,
        require_published: bool,
    ):
        registry = ArtifactRegistryService(self.db)
        if pinned_revision_id is not None:
            revision = await registry.get_revision(revision_id=pinned_revision_id, tenant_id=self.tenant_id)
            if revision is None:
                raise ValueError("Pinned artifact revision not found")
            if require_published and (not revision.is_published or revision.is_ephemeral):
                raise PermissionError("Production artifact execution requires a published immutable revision")
            return revision

        artifact = await registry.get_tenant_artifact(artifact_id=artifact_id, tenant_id=self.tenant_id)
        if artifact is None:
            raise ValueError(f"Artifact '{artifact_id}' not found")
        if artifact.kind != ArtifactKind.AGENT_NODE:
            raise ValueError(f"Artifact '{artifact_id}' is not an agent_node artifact")
        revision = artifact.latest_published_revision if require_published else (artifact.latest_draft_revision or artifact.latest_published_revision)
        if revision is None:
            raise ValueError(f"Artifact '{artifact_id}' has no executable revision")
        if require_published and (not revision.is_published or revision.is_ephemeral):
            raise PermissionError("Production artifact execution requires a published immutable revision")
        return revision

    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate that the artifact exists and is properly configured."""
        artifact_id = config.get("_artifact_id")
        if not artifact_id:
            return ValidationResult(valid=False, errors=["Missing artifact ID in config"])

        artifact_uuid = self._parse_uuid(artifact_id)
        if artifact_uuid is None:
            return ValidationResult(valid=False, errors=["Artifact nodes now require a UUID artifact id"])
        if self.db is None:
            return ValidationResult(valid=True)
        artifact = await ArtifactRegistryService(self.db).get_tenant_artifact(artifact_id=artifact_uuid, tenant_id=self.tenant_id)
        if artifact is None:
            return ValidationResult(valid=False, errors=[f"Artifact '{artifact_id}' not found"])
        if artifact.kind != ArtifactKind.AGENT_NODE:
            return ValidationResult(valid=False, errors=[f"Artifact '{artifact_id}' is not an agent_node artifact"])
        return ValidationResult(valid=True)
    
    async def execute(
        self, 
        state: Dict[str, Any], 
        config: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an artifact handler.
        
        Args:
            state: Current agent state (messages, state variables, etc.)
            config: Node configuration including _artifact_id and _artifact_version
            context: Execution context (node_id, emitter, etc.)
            
        Returns:
            State update dictionary to merge with agent state.
        """
        artifact_id = config.get("_artifact_id")
        artifact_revision_id = self._parse_uuid(config.get("_artifact_revision_id"))
        
        if not artifact_id:
            raise ValueError("Missing _artifact_id in config")

        artifact_uuid = self._parse_uuid(artifact_id)
        production_mode = self._is_production_mode(context)

        # Get emitter for tracing
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", artifact_id) if context else artifact_id
        node_name = config.get("label", str(artifact_id))
        
        # Emit node start event
        if emitter:
            emitter.emit_node_start(node_id, node_name, f"artifact:{artifact_id}", {
                "artifact_id": artifact_id,
                "config_keys": list(config.keys())
            })
        
        try:
            # Filter out internal config keys before passing to handler
            handler_config = {k: v for k, v in config.items() if not k.startswith("_")}
            from app.agent.execution.field_resolver import resolve_artifact_inputs

            artifact_inputs = None
            if artifact_uuid is not None:
                revision = await self._resolve_tenant_revision(
                    artifact_id=artifact_uuid,
                    pinned_revision_id=artifact_revision_id,
                    require_published=production_mode,
                )
                artifact_inputs = _input_specs_from_schema((revision.agent_contract or {}).get("input_schema"))

            # Resolve inputs from state using mappings
            resolved_inputs = resolve_artifact_inputs(
                state=state,
                config=config,
                artifact_inputs=artifact_inputs,
                strict=config.get("_strict_validation", False)
            )

            exec_context = {
                **(context or {}),
                "artifact_id": artifact_id,
                "artifact_revision_id": str(artifact_revision_id) if artifact_revision_id else None,
                "emitter": emitter,
                "tenant_id": self.tenant_id,
                "inputs": resolved_inputs,
                "agent_id": (context or {}).get("agent_id"),
                "agent_slug": (context or {}).get("agent_slug"),
                "auth": {
                    "grant_id": (context or {}).get("grant_id"),
                    "principal_id": (context or {}).get("principal_id"),
                    "initiator_user_id": (context or {}).get("initiator_user_id"),
                    "run_id": (context or {}).get("run_id"),
                },
            }

            run = await ArtifactExecutionService(self.db).execute_live_run(
                tenant_id=self.tenant_id,
                created_by=self._parse_uuid((context or {}).get("initiator_user_id")),
                revision_id=revision.id,
                domain=ArtifactRunDomain.AGENT,
                queue_class="artifact_prod_interactive",
                input_payload=resolved_inputs,
                config_payload=handler_config,
                context_payload=exec_context,
                require_published=production_mode,
            )
            if run is None:
                raise RuntimeError("Artifact execution did not return a run")
            if run.status != ArtifactRunStatus.COMPLETED:
                error_message = ((run.error_payload or {}).get("message") if isinstance(run.error_payload, dict) else None) or "Artifact execution failed"
                raise RuntimeError(error_message)
            result = run.result_payload or {}
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}
            
            # Emit node end event
            if emitter:
                emitter.emit_node_end(node_id, node_name, f"artifact:{artifact_id}", {
                    "success": True,
                    "result_keys": list(result.keys())
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Artifact execution failed [{artifact_id}]: {e}", exc_info=True)
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise
