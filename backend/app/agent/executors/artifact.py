"""
ArtifactNodeExecutor - Executes artifact-based agent nodes.

This executor dynamically loads and runs artifact handlers for agent nodes,
providing full tracing, error handling, and state management.
"""
import asyncio
import logging
import importlib
from typing import Any, Dict, Optional

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.services.artifact_registry import get_artifact_registry

logger = logging.getLogger(__name__)


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
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate that the artifact exists and is properly configured."""
        artifact_id = config.get("_artifact_id")
        if not artifact_id:
            return ValidationResult(valid=False, errors=["Missing artifact ID in config"])
        
        registry = get_artifact_registry()
        if not registry.get_artifact(artifact_id):
            return ValidationResult(valid=False, errors=[f"Artifact '{artifact_id}' not found"])
        
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
        artifact_version = config.get("_artifact_version")
        
        if not artifact_id:
            raise ValueError("Missing _artifact_id in config")
        
        registry = get_artifact_registry()
        spec = registry.get_artifact(artifact_id, artifact_version)
        
        if not spec:
            raise ValueError(f"Artifact '{artifact_id}' not found")
        
        # Get emitter for tracing
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", artifact_id) if context else artifact_id
        node_name = config.get("label", spec.display_name)
        
        # Emit node start event
        if emitter:
            emitter.emit_node_start(node_id, node_name, f"artifact:{artifact_id}", {
                "artifact_id": artifact_id,
                "version": spec.version,
                "config_keys": list(config.keys())
            })
        
        try:
            # Load handler module
            module_path = registry.get_handler_module_path(artifact_id, artifact_version)
            if not module_path:
                raise ValueError(f"No handler found for artifact '{artifact_id}'")
            
            logger.debug(f"Loading artifact handler: {module_path}")
            
            # Import the handler module
            try:
                module = importlib.import_module(module_path)
            except ImportError as e:
                raise ValueError(f"Failed to import artifact handler '{module_path}': {e}")
            
            execute_fn = getattr(module, "execute", None)
            
            if not execute_fn:
                raise ValueError(f"Artifact '{artifact_id}' handler missing execute() function")
            
            # Filter out internal config keys before passing to handler
            handler_config = {k: v for k, v in config.items() if not k.startswith("_")}
            
            # NEW: Resolve input fields using field mappings
            from app.agent.execution.field_resolver import resolve_artifact_inputs
            
            # Get artifact's declared inputs from the YAML manifest
            artifact_path = registry.get_artifact_path(artifact_id, artifact_version)
            artifact_inputs = None
            if artifact_path:
                import yaml
                manifest_path = artifact_path / "artifact.yaml"
                if manifest_path.exists():
                    with open(manifest_path) as f:
                        manifest = yaml.safe_load(f)
                    artifact_inputs = manifest.get("inputs", [])
            
            # Resolve inputs from state using mappings
            resolved_inputs = resolve_artifact_inputs(
                state=state,
                config=config,
                artifact_inputs=artifact_inputs,
                strict=config.get("_strict_validation", False)
            )
            
            # Prepare execution context with both resolved inputs and full state
            async def _mint_workload_token(scope_subset: Optional[list[str]] = None, audience: str = "talmudpedia-internal-api") -> Optional[str]:
                grant_id = (context or {}).get("grant_id")
                if not grant_id:
                    raise PermissionError("Missing delegation grant context for workload token minting")
                from uuid import UUID
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

            exec_context = {
                **(context or {}),
                "artifact_id": artifact_id,
                "artifact_version": spec.version,
                "emitter": emitter,
                "tenant_id": self.tenant_id,
                "inputs": resolved_inputs,  # Structured resolved inputs
                "auth": {
                    "grant_id": (context or {}).get("grant_id"),
                    "principal_id": (context or {}).get("principal_id"),
                    "initiator_user_id": (context or {}).get("initiator_user_id"),
                    "run_id": (context or {}).get("run_id"),
                    "mint_token": _mint_workload_token,
                },
            }
            
            # Execute handler (support both sync and async)
            # Pass resolved_inputs as first arg if handler supports it, else fall back to state
            if asyncio.iscoroutinefunction(execute_fn):
                result = await execute_fn(state, handler_config, exec_context)
            else:
                # Run sync function in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, 
                    lambda: execute_fn(state, handler_config, exec_context)
                )
            
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
