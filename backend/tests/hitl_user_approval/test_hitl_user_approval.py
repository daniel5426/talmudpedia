import pytest

from app.agent.executors.interaction import HumanInputNodeExecutor


@pytest.mark.asyncio
async def test_user_approval_can_execute_gates_on_payload():
    executor = HumanInputNodeExecutor(organization_id=None, db=None)

    can_execute = await executor.can_execute({}, {}, {"node_type": "user_approval"})
    assert can_execute is False

    can_execute = await executor.can_execute({"approval": "approve"}, {}, {"node_type": "user_approval"})
    assert can_execute is True


@pytest.mark.asyncio
async def test_user_approval_execute_approve_reject():
    executor = HumanInputNodeExecutor(organization_id=None, db=None)

    approved = await executor.execute({"approval": "yes"}, {}, {"node_type": "user_approval"})
    assert approved["branch_taken"] == "approve"
    assert approved["approval_status"] == "approved"

    rejected = await executor.execute({"approval": "reject"}, {}, {"node_type": "user_approval"})
    assert rejected["branch_taken"] == "reject"
    assert rejected["approval_status"] == "rejected"


@pytest.mark.asyncio
async def test_user_approval_rejects_invalid_payload():
    executor = HumanInputNodeExecutor(organization_id=None, db=None)

    with pytest.raises(ValueError):
        await executor.execute({"approval": "maybe"}, {}, {"node_type": "user_approval"})


@pytest.mark.asyncio
async def test_user_approval_allows_non_interaction_nodes_to_continue():
    executor = HumanInputNodeExecutor(organization_id=None, db=None)

    can_execute = await executor.can_execute({}, {}, {"node_type": "agent"})
    assert can_execute is True
