import asyncio
import os
import uuid
from app.db.postgres.models.agents import Agent
from app.db.postgres.engine import sessionmaker
from app.agent.execution.service import AgentExecutorService

async def reproduce():
    # Make sure env vars for LLM are set (e.g. OPENAI_API_KEY or GOOGLE_API_KEY)
    # We'll assume they are in the environment
    
    async with sessionmaker() as session:
        # Create a test agent with an LLM node
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            name="Stall Test Agent",
            slug=f"stall-test-{agent_id.hex[:8]}",
            tenant_id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            graph_definition={
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                    {"id": "llm", "type": "llm", "position": {"x": 200, "y": 0}, "config": {"model_id": "gemini-pro"}}, # Adjust model_id as needed
                    {"id": "end", "type": "end", "position": {"x": 400, "y": 0}}
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "llm"},
                    {"id": "e2", "source": "llm", "target": "end"}
                ]
            },
            version=1,
            status="published"
        )
        session.add(agent)
        await session.commit()
        
        executor = AgentExecutorService(db=session)
        
        print("Starting run...")
        # Simulate the input params structure we just fixed
        input_params = {
            "messages": [{"role": "user", "content": "Hello LLM"}],
            "input": "Hello LLM"
        }
        
        run_id = await executor.start_run(agent_id, input_params, background=False)
        print(f"Run started: {run_id}")
        
        print("Streaming events...")
        async for event in executor.run_and_stream(run_id, session):
            print(f"Event: {event.get('event') or event.get('type')}")
            if event.get("event") == "run_status":
                print(f"Final Status: {event.get('status')}")

if __name__ == "__main__":
    asyncio.run(reproduce())
