import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.agent.executors.base import BaseNodeExecutor
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.orchestration_policy_service import (
    ORCHESTRATION_SURFACE_OPTION_A,
    is_orchestration_surface_enabled,
)


class _BaseOrchestrationExecutor(BaseNodeExecutor):
    def _require_kernel(self) -> OrchestrationKernelService:
        if self.db is None:
            raise ValueError("Orchestration executors require a DB session")
        return OrchestrationKernelService(self.db)

    def _caller_run_id(self, state: Dict[str, Any], context: Optional[Dict[str, Any]]) -> UUID:
        run_id = self._as_text((context or {}).get("run_id"))
        if run_id is None and isinstance(state.get("context"), dict):
            run_id = self._as_text(state.get("context", {}).get("run_id"))
        if run_id is None:
            raise ValueError("Missing caller run context for orchestration node execution")
        return UUID(run_id)

    def _node_id(self, context: Optional[Dict[str, Any]], fallback: str) -> str:
        return self._as_text((context or {}).get("node_id")) or fallback

    def _effective_tenant_id(self, state: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Optional[str]:
        from_context = self._as_text((context or {}).get("tenant_id"))
        if from_context:
            return from_context
        if isinstance((context or {}).get("state_context"), dict):
            from_state_ctx = self._as_text((context or {}).get("state_context", {}).get("tenant_id"))
            if from_state_ctx:
                return from_state_ctx
        if isinstance(state.get("context"), dict):
            from_state = self._as_text(state.get("context", {}).get("tenant_id"))
            if from_state:
                return from_state
        if self.tenant_id:
            return str(self.tenant_id)
        return None

    def _assert_option_a_enabled(self, state: Dict[str, Any], context: Optional[Dict[str, Any]]) -> None:
        tenant_id = self._effective_tenant_id(state, context)
        if is_orchestration_surface_enabled(
            surface=ORCHESTRATION_SURFACE_OPTION_A,
            tenant_id=tenant_id,
        ):
            return
        raise PermissionError("GraphSpec v2 orchestration is disabled by feature flag for this tenant")

    def _event_emitter(self, context: Optional[Dict[str, Any]]):
        emitter = (context or {}).get("emitter")
        if emitter is not None:
            return emitter
        from app.agent.execution.emitter import active_emitter
        return active_emitter.get()

    def _emit_policy_deny(
        self,
        *,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        node_id: str,
        action: str,
        reason: str,
    ) -> None:
        emitter = self._event_emitter(context)
        if emitter is not None:
            emitter.emit_orchestration_policy_deny(
                node_id=node_id,
                action=action,
                reason=reason,
            )

    def _emit_spawn_events(
        self,
        *,
        context: Optional[Dict[str, Any]],
        node_id: str,
        target_agent_id: Optional[str],
        target_agent_slug: Optional[str],
        result: Dict[str, Any],
    ) -> None:
        emitter = self._event_emitter(context)
        if emitter is None:
            return
        spawned_ids = [str(item) for item in (result.get("spawned_run_ids") or []) if item]
        emitter.emit_orchestration_spawn_decision(
            node_id=node_id,
            target_agent_id=target_agent_id,
            target_agent_slug=target_agent_slug,
            spawned_run_ids=spawned_ids,
            idempotent=bool(result.get("idempotent")),
        )
        group_id = self._as_text(result.get("orchestration_group_id") or result.get("group_id"))
        for run_id in spawned_ids:
            emitter.emit_orchestration_child_lifecycle(
                node_id=node_id,
                child_run_id=run_id,
                lifecycle_status="queued",
                orchestration_group_id=group_id,
            )

    def _emit_join_decision(
        self,
        *,
        context: Optional[Dict[str, Any]],
        node_id: str,
        result: Dict[str, Any],
    ) -> None:
        emitter = self._event_emitter(context)
        if emitter is None:
            return
        emitter.emit_orchestration_join_decision(
            node_id=node_id,
            group_id=self._as_text(result.get("group_id")) or "",
            mode=self._as_text(result.get("mode")) or "best_effort",
            status=self._as_text(result.get("status")) or "running",
            complete=bool(result.get("complete")),
            success_count=int(result.get("success_count") or 0),
            failure_count=int(result.get("failure_count") or 0),
            running_count=int(result.get("running_count") or 0),
        )

    def _emit_cancellation_propagation(
        self,
        *,
        context: Optional[Dict[str, Any]],
        node_id: str,
        payload: Dict[str, Any],
    ) -> None:
        emitter = self._event_emitter(context)
        if emitter is None:
            return
        run_ids = payload.get("run_ids") if isinstance(payload.get("run_ids"), list) else []
        emitter.emit_orchestration_cancellation_propagation(
            node_id=node_id,
            reason=self._as_text(payload.get("reason")),
            cancelled_run_ids=[str(item) for item in run_ids if item],
            include_root=bool(payload["include_root"]) if "include_root" in payload else None,
        )

    @staticmethod
    def _as_text(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _as_uuid(value: Any) -> Optional[UUID]:
        text = _BaseOrchestrationExecutor._as_text(value)
        if text is None:
            return None
        try:
            return UUID(text)
        except Exception:
            return None

    @staticmethod
    def _normalize_scope_subset(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str) and item.strip()]
        return []

    def _resolve_scope_subset(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> List[str]:
        from_config = self._normalize_scope_subset(config.get("scope_subset"))
        if from_config:
            return from_config
        if isinstance((context or {}).get("state_context"), dict):
            from_state_ctx = self._normalize_scope_subset(
                (context or {}).get("state_context", {}).get("requested_scopes")
            )
            if from_state_ctx:
                return from_state_ctx
        if isinstance(state.get("context"), dict):
            from_state = self._normalize_scope_subset(state.get("context", {}).get("requested_scopes"))
            if from_state:
                return from_state
        return []

    def _stable_idempotency_key(
        self,
        *,
        explicit_key: Optional[str],
        run_id: UUID,
        node_id: str,
        salt: Dict[str, Any],
    ) -> str:
        if explicit_key and explicit_key.strip():
            return explicit_key.strip()
        payload = {"run_id": str(run_id), "node_id": node_id, "salt": salt}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"{node_id}:{digest[:20]}"

    def _latest_group_id(self, state: Dict[str, Any]) -> Optional[UUID]:
        outputs = state.get("_node_outputs")
        if not isinstance(outputs, dict):
            return None
        for item in reversed(list(outputs.values())):
            if not isinstance(item, dict):
                continue
            group_id = self._as_uuid(item.get("orchestration_group_id") or item.get("group_id"))
            if group_id is not None:
                return group_id
        return None

    def _latest_spawned_run_id(self, state: Dict[str, Any]) -> Optional[UUID]:
        outputs = state.get("_node_outputs")
        if not isinstance(outputs, dict):
            return None
        for item in reversed(list(outputs.values())):
            if not isinstance(item, dict):
                continue
            spawned_ids = item.get("spawned_run_ids")
            if isinstance(spawned_ids, list) and spawned_ids:
                run_uuid = self._as_uuid(spawned_ids[0])
                if run_uuid is not None:
                    return run_uuid
            run_id = self._as_uuid(item.get("run_id"))
            if run_id is not None:
                return run_id
        return None

    def _latest_orchestration_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        outputs = state.get("_node_outputs")
        if not isinstance(outputs, dict):
            return {}
        for item in reversed(list(outputs.values())):
            if isinstance(item, dict):
                return item
        return {}


class SpawnRunNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        node_id = self._node_id(context, "spawn_run")
        try:
            self._assert_option_a_enabled(state, context)
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="spawn_run",
                reason=str(exc),
            )
            raise
        kernel = self._require_kernel()
        caller_run_id = self._caller_run_id(state, context)

        mapped_input_payload = config.get("mapped_input_payload")
        if not isinstance(mapped_input_payload, dict):
            mapped_input_payload = {}

        scope_subset = self._resolve_scope_subset(state, config, context)
        idempotency_key = self._stable_idempotency_key(
            explicit_key=self._as_text(config.get("idempotency_key")),
            run_id=caller_run_id,
            node_id=node_id,
            salt={
                "target_agent_id": self._as_text(config.get("target_agent_id")),
                "target_agent_slug": self._as_text(config.get("target_agent_slug")),
                "mapped_input_payload": mapped_input_payload,
                "scope_subset": scope_subset,
            },
        )

        target_agent_id = self._as_uuid(config.get("target_agent_id"))
        target_agent_slug = self._as_text(config.get("target_agent_slug"))
        try:
            result = await kernel.spawn_run(
                caller_run_id=caller_run_id,
                parent_node_id=self._as_text((context or {}).get("node_id")),
                target_agent_id=target_agent_id,
                target_agent_slug=target_agent_slug,
                mapped_input_payload=mapped_input_payload,
                failure_policy=self._as_text(config.get("failure_policy")),
                timeout_s=config.get("timeout_s"),
                scope_subset=scope_subset,
                idempotency_key=idempotency_key,
                start_background=bool(config.get("start_background", True)),
                orchestration_group_id=self._as_uuid(config.get("orchestration_group_id")),
            )
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="spawn_run",
                reason=str(exc),
            )
            raise
        spawned = result.get("spawned_run_ids") if isinstance(result, dict) else None
        if isinstance(spawned, list) and spawned:
            result["run_id"] = spawned[0]
        self._emit_spawn_events(
            context=context,
            node_id=node_id,
            target_agent_id=str(target_agent_id) if target_agent_id else None,
            target_agent_slug=target_agent_slug,
            result=result,
        )
        return result


class SpawnGroupNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        node_id = self._node_id(context, "spawn_group")
        try:
            self._assert_option_a_enabled(state, context)
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="spawn_group",
                reason=str(exc),
            )
            raise
        kernel = self._require_kernel()
        caller_run_id = self._caller_run_id(state, context)

        raw_targets = config.get("targets")
        targets = raw_targets if isinstance(raw_targets, list) else []
        scope_subset = self._resolve_scope_subset(state, config, context)
        id_prefix = self._as_text(config.get("idempotency_key_prefix"))
        if not id_prefix:
            id_prefix = self._stable_idempotency_key(
                explicit_key=None,
                run_id=caller_run_id,
                node_id=node_id,
                salt={
                    "targets": targets,
                    "scope_subset": scope_subset,
                },
            )

        try:
            result = await kernel.spawn_group(
                caller_run_id=caller_run_id,
                parent_node_id=self._as_text((context or {}).get("node_id")),
                targets=[item for item in targets if isinstance(item, dict)],
                failure_policy=self._as_text(config.get("failure_policy")),
                join_mode=self._as_text(config.get("join_mode")) or "all",
                quorum_threshold=config.get("quorum_threshold"),
                timeout_s=config.get("timeout_s"),
                scope_subset=scope_subset,
                idempotency_key_prefix=id_prefix,
                start_background=bool(config.get("start_background", True)),
            )
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="spawn_group",
                reason=str(exc),
            )
            raise
        self._emit_spawn_events(
            context=context,
            node_id=node_id,
            target_agent_id=None,
            target_agent_slug=None,
            result=result,
        )
        return result


class JoinNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        node_id = self._node_id(context, "join")
        try:
            self._assert_option_a_enabled(state, context)
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="join",
                reason=str(exc),
            )
            raise
        kernel = self._require_kernel()
        caller_run_id = self._caller_run_id(state, context)

        group_id = self._as_uuid(config.get("orchestration_group_id"))
        if group_id is None:
            group_id = self._latest_group_id(state)
        if group_id is None:
            raise ValueError("join requires orchestration_group_id")

        result = await kernel.join(
            caller_run_id=caller_run_id,
            orchestration_group_id=group_id,
            mode=self._as_text(config.get("mode")),
            quorum_threshold=config.get("quorum_threshold"),
            timeout_s=config.get("timeout_s"),
        )
        self._emit_join_decision(context=context, node_id=node_id, result=result)
        cancellation = result.get("cancellation_propagated")
        if isinstance(cancellation, dict) and int(cancellation.get("count") or 0) > 0:
            self._emit_cancellation_propagation(
                context=context,
                node_id=node_id,
                payload={
                    "reason": cancellation.get("reason"),
                    "run_ids": cancellation.get("run_ids") or [],
                },
            )

        status = self._as_text(result.get("status")) or "running"
        complete = bool(result.get("complete"))
        if not complete:
            route_key = "pending"
        elif status in {"completed", "completed_with_errors", "failed", "timed_out"}:
            route_key = status
        else:
            route_key = "completed"
        result["next"] = route_key
        result["branch_taken"] = route_key
        return result


class RouterNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        payload = self._latest_orchestration_payload(state)
        routes = config.get("routes")
        routes = routes if isinstance(routes, list) else []

        route_key = self._as_text(config.get("route_key")) or "status"
        value = payload.get(route_key)
        branch = "default"

        for idx, item in enumerate(routes):
            if isinstance(item, str):
                name = item
                match_value = item
            elif isinstance(item, dict):
                name = self._as_text(item.get("name")) or self._as_text(item.get("handle")) or f"route_{idx}"
                match_value = item.get("match")
                if match_value is None and "value" in item:
                    match_value = item.get("value")
            else:
                continue

            if value == match_value:
                branch = name
                break

        return {
            "next": branch,
            "branch_taken": branch,
            "router_value": value,
        }


class JudgeNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        payload = self._latest_orchestration_payload(state)
        outcomes = config.get("outcomes")
        outcomes = [o for o in outcomes if isinstance(o, str) and o.strip()] if isinstance(outcomes, list) else []
        configured_pass = self._as_text(config.get("pass_outcome"))
        configured_fail = self._as_text(config.get("fail_outcome"))
        pass_outcome = outcomes[0] if outcomes else (configured_pass or "pass")
        fail_outcome = outcomes[1] if len(outcomes) > 1 else (configured_fail or "fail")

        suggested_action = self._as_text(payload.get("suggested_action"))
        status = self._as_text(payload.get("status"))

        if suggested_action == "replan":
            chosen = fail_outcome
        elif status in {"completed", "completed_with_errors"}:
            chosen = pass_outcome
        else:
            chosen = fail_outcome

        return {
            "next": chosen,
            "branch_taken": chosen,
            "judge_input": {
                "status": status,
                "suggested_action": suggested_action,
            },
        }


class ReplanNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        node_id = self._node_id(context, "replan")
        try:
            self._assert_option_a_enabled(state, context)
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="replan",
                reason=str(exc),
            )
            raise
        kernel = self._require_kernel()
        caller_run_id = self._caller_run_id(state, context)

        run_id = self._as_uuid(config.get("run_id"))
        if run_id is None:
            run_id = self._latest_spawned_run_id(state)
        if run_id is None:
            raise ValueError("replan requires run_id")

        result = await kernel.evaluate_and_replan(
            caller_run_id=caller_run_id,
            run_id=run_id,
        )
        next_key = "replan" if bool(result.get("needs_replan")) else "continue"
        result["next"] = next_key
        result["branch_taken"] = next_key
        return result


class CancelSubtreeNodeExecutor(_BaseOrchestrationExecutor):
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        node_id = self._node_id(context, "cancel_subtree")
        try:
            self._assert_option_a_enabled(state, context)
        except PermissionError as exc:
            self._emit_policy_deny(
                state=state,
                context=context,
                node_id=node_id,
                action="cancel_subtree",
                reason=str(exc),
            )
            raise
        kernel = self._require_kernel()
        caller_run_id = self._caller_run_id(state, context)

        run_id = self._as_uuid(config.get("run_id"))
        if run_id is None:
            run_id = self._latest_spawned_run_id(state)
        if run_id is None:
            raise ValueError("cancel_subtree requires run_id")

        result = await kernel.cancel_subtree(
            caller_run_id=caller_run_id,
            run_id=run_id,
            include_root=bool(config.get("include_root", True)),
            reason=self._as_text(config.get("reason")),
        )
        if int(result.get("cancelled_count") or 0) > 0:
            self._emit_cancellation_propagation(
                context=context,
                node_id=node_id,
                payload={
                    "reason": self._as_text(config.get("reason")) or "cancelled_by_orchestration",
                    "run_ids": result.get("cancelled_run_ids") or [],
                    "include_root": bool(config.get("include_root", True)),
                },
            )
        return result
