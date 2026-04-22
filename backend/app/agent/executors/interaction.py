import logging
from typing import Any, Dict
from app.agent.executors.base import BaseNodeExecutor

logger = logging.getLogger(__name__)

class HumanInputNodeExecutor(BaseNodeExecutor):
    async def can_execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> bool:
        """
        Wait until the approval payload is present.
        """
        node_type = context.get("node_type") if context else None
        if node_type == "user_approval":
            return "approval" in state
        return True

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        node_type = context.get("node_type") if context else None
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", node_type or "user_approval") if context else (node_type or "user_approval")
        node_name = context.get("node_name", node_type or "User Approval") if context else (node_type or "User Approval")

        if emitter:
            emitter.emit_node_start(node_id, node_name, node_type or "user_approval")

        if node_type == "user_approval":
            approval = state.get("approval")
            comment = state.get("comment")
            normalized = str(approval).lower() if approval is not None else ""

            if normalized in ("approved", "approve", "true", "yes", "1"):
                branch = "approve"
                status = "approved"
            elif normalized in ("rejected", "reject", "false", "no", "0"):
                branch = "reject"
                status = "rejected"
            else:
                raise ValueError("Missing or invalid approval payload")

            result = {
                "approval_status": status,
                "branch_taken": branch,
                "next": branch,
                "context": {"comment": comment} if comment is not None else {},
            }
            if emitter:
                emitter.emit_node_end(node_id, node_name, "user_approval", {"branch_taken": branch})
            return result

        logger.info("Executed User Approval Node (default)")
        if emitter:
            emitter.emit_node_end(node_id, node_name, node_type or "user_approval")
        return {}
