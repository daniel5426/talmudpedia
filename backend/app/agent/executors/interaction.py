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

            return {
                "approval_status": status,
                "branch_taken": branch,
                "next": branch,
                "context": {"comment": comment} if comment is not None else {},
            }

        if node_type == "human_input":
            message = state.get("input") or state.get("message")
            if message is None:
                raise ValueError("Missing human input payload")
            return {
                "messages": [{"role": "user", "content": str(message)}]
            }

        logger.info("Executed Human Input Node (default)")
        return {}
