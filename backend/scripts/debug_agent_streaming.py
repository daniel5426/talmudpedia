#!/usr/bin/env python3
"""
Debug script to test agent streaming directly from the backend.
Run this to see what events are actually being emitted.
"""

import asyncio
import sys
import os
sys.path.insert(0, "/Users/danielbenassaya/Code/personal/talmudpedia/backend")

# Set up environment
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")

import json

async def test_agent_streaming():
    """
    Test the agent streaming flow directly to see what events are emitted.
    """
    from app.agent.graph.schema import AgentGraph, NodeType, EdgeType, MemoryConfig, ExecutionConstraints
    from app.agent.graph.compiler import AgentCompiler
    from uuid import uuid4
    
    print("=" * 60)
    print("Testing Agent Streaming Flow")
    print("=" * 60)
    
    # Create a simple test graph with LLM node
    graph = AgentGraph(
        nodes=[
            {"id": "start", "type": NodeType.START, "position": {"x": 0, "y": 0}},
            {"id": "llm", "type": NodeType.LLM, "position": {"x": 100, "y": 0}, "config": {"model_id": "test-model"}},
            {"id": "end", "type": NodeType.END, "position": {"x": 200, "y": 0}},
        ],
        edges=[
            {"id": "e1", "source": "start", "target": "llm", "type": EdgeType.CONTROL},
            {"id": "e2", "source": "llm", "target": "end", "type": EdgeType.CONTROL},
        ]
    )
    
    memory_config = MemoryConfig()
    execution_constraints = ExecutionConstraints()
    
    # Compile without DB (mock mode)
    compiler = AgentCompiler(tenant_id=None, db=None)
    
    try:
        executable = await compiler.compile(
            agent_id=uuid4(),
            version=1,
            graph=graph,
            memory_config=memory_config,
            execution_constraints=execution_constraints,
        )
        print("✓ Agent compiled successfully")
    except Exception as e:
        print(f"✗ Compilation failed: {e}")
        return
    
    # Test streaming
    input_data = {
        "messages": [{"role": "user", "content": "Hello, test message"}],
        "steps": []
    }
    
    print("\nStreaming events:")
    print("-" * 60)
    
    event_count = 0
    chat_model_stream_count = 0
    
    try:
        async for event in executable.stream(input_data):
            event_count += 1
            event_type = event.get("event", "unknown")
            event_name = event.get("name", "")
            
            print(f"Event {event_count}: type={event_type}, name={event_name}")
            
            # Check for chat model stream events
            if event_type == "on_chat_model_stream":
                chat_model_stream_count += 1
                chunk = event.get("data", {}).get("chunk", {})
                content = chunk.get("content", "") if isinstance(chunk, dict) else ""
                print(f"  → Content chunk: '{content}'")
            
            # Show the full event for the first few
            if event_count <= 5:
                print(f"  Full event: {json.dumps(event, default=str)[:500]}")
                
    except Exception as e:
        print(f"✗ Streaming failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("-" * 60)
    print(f"\nTotal events: {event_count}")
    print(f"Chat model stream events: {chat_model_stream_count}")
    
    if chat_model_stream_count == 0:
        print("\n⚠️  No 'on_chat_model_stream' events were emitted!")
        print("This means the LLM adapter is not properly emitting token callbacks.")
        print("The frontend relies on these events to display the AI response.")
    else:
        print("\n✓ Chat model stream events were emitted correctly.")


if __name__ == "__main__":
    asyncio.run(test_agent_streaming())
