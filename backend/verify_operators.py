import asyncio
import logging
from typing import Dict, Any

from app.agent.executors.standard import StartNodeExecutor, EndNodeExecutor
from app.agent.executors.data import TransformNodeExecutor, SetStateNodeExecutor
from app.agent.executors.logic import IfElseNodeExecutor, WhileNodeExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_verification():
    logger.info("Starting verification of new operators...")
    
    # Mock tenant and db
    tenant_id = "test_tenant"
    db = None
    
    # Initialize executors
    start_exec = StartNodeExecutor(tenant_id, db)
    transform_exec = TransformNodeExecutor(tenant_id, db)
    set_state_exec = SetStateNodeExecutor(tenant_id, db)
    if_else_exec = IfElseNodeExecutor(tenant_id, db)
    while_exec = WhileNodeExecutor(tenant_id, db)
    end_exec = EndNodeExecutor(tenant_id, db)
    
    # Initial state
    workflow_state = {
        "state": {"val": 5},
        "loop_counters": {},
        "execution_history": []
    }
    
    # 1. Start
    logger.info(f"Step 1: Start (val=5)")
    
    # 2. Transform: val = val * 2 (expect 10)
    logger.info("Step 2: Transform (val = val * 2)")
    result = await transform_exec.execute(workflow_state, {
        "mappings": [{"key": "val", "value": "state.val * 2"}]
    })
    workflow_state["state"].update(result["state"])
    logger.info(f"  Result: val={workflow_state['state']['val']}")
    assert workflow_state['state']['val'] == 10
    
    # 3. If/Else: val > 15? (expect False -> else)
    logger.info("Step 3: If/Else (val > 15?)")
    result = await if_else_exec.execute(workflow_state, {
        "conditions": [{"name": "high", "expression": "state.val > 15"}]
    })
    branch = result.get("next") or result.get("branch_taken")
    logger.info(f"  Result: branch={branch}")
    assert branch == "else"
    
    # 4. Set State: status = "processing"
    logger.info("Step 4: Set State (status = 'processing')")
    result = await set_state_exec.execute(workflow_state, {
        "assignments": [{"variable": "status", "value": "processing"}]
    })
    workflow_state["state"].update(result["state"])
    logger.info(f"  Result: status={workflow_state['state']['status']}")
    assert workflow_state['state']['status'] == "processing"
    
    # 5. While Loop: val < 25 (val starts at 10)
    logger.info("Step 5: While Loop (val < 25)")
    config = {
        "condition": "state.val < 25",
        "name": "loop1",
        "max_iterations": 5
    }
    
    iterations = 0
    while True:
        result = await while_exec.execute(workflow_state, config)
        next_step = result.get("next")
        logger.info(f"  Loop check (val={workflow_state['state']['val']}): {next_step}")
        
        if next_step == "exit":
            break
            
        iterations += 1
        # Simulate loop body: Transform val = val + 5
        logger.info("    Loop body: val = val + 5")
        res = await transform_exec.execute(workflow_state, {
            "mappings": [{"key": "val", "value": "state.val + 5"}]
        })
        workflow_state["state"].update(res["state"])
        
        # Update loop counter manually (normally handled by engine)
        workflow_state["loop_counters"]["loop1"] = workflow_state["loop_counters"].get("loop1", 0) + 1
        
    logger.info(f"  Loop finished after {iterations} iterations")
    logger.info(f"  Final val: {workflow_state['state']['val']}")
    
    # Expected: 10 -> 15 -> 20 -> 25 (exit) => 3 iterations
    assert workflow_state['state']['val'] == 25
    assert iterations == 3
    
    logger.info("✅ All verifications passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_verification())
