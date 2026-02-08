import logging
from typing import Any, Dict
from app.agent.executors.base import BaseNodeExecutor

logger = logging.getLogger(__name__)

class HumanInputNodeExecutor(BaseNodeExecutor):
    async def can_execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> bool:
        """
        Check if we have received input.
        If state contains the expected input for this node ID, proceed.
        Otherwise return False to suspend execution.
        """
        node_type = context.get("node_type") if context else None
        if node_type == "user_approval":
            return "approval" in state
        if node_type == "human_input":
            return "input" in state or "message" in state
        return True

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        node_type = context.get("node_type") if context else None
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", node_type or "human_input") if context else (node_type or "human_input")
        node_name = context.get("node_name", node_type or "Human Input") if context else (node_type or "Human Input")

        if emitter:
            emitter.emit_node_start(node_id, node_name, node_type or "human_input")

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

        if node_type == "human_input":
            message = state.get("input") or state.get("message")
            if message is None:
                raise ValueError("Missing human input payload")
            result = {
                "messages": [{"role": "user", "content": str(message)}]
            }
            if emitter:
                emitter.emit_node_end(node_id, node_name, "human_input", {"has_message": True})
            return result

        logger.info("Executed Human Input Node (default)")
        if emitter:
            emitter.emit_node_end(node_id, node_name, node_type or "human_input")
        return {}
