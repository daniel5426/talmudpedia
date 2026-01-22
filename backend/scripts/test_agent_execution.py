#!/usr/bin/env python3
"""
Test script to verify agent execution and identify the empty response bug.

This script tests the agent streaming pipeline to identify why empty responses are returned.
"""

import asyncio
import sys
sys.path.insert(0, "/Users/danielbenassaya/Code/personal/talmudpedia/backend")

# Test 1: Check for syntax errors in the compiler module by simply importing it
def test_compiler_imports():
    """Test that the compiler module can be imported without errors."""
    print("Test 1: Testing compiler imports...")
    try:
        from app.agent.graph.compiler import AgentCompiler, ValidationError
        from app.agent.graph.schema import AgentGraph, AgentNode, AgentEdge, NodeType
        from app.agent.graph.executable import ExecutableAgent
        print("  ✓ All compiler modules imported successfully")
        return True
    except Exception as e:
        print(f"  ✗ Import error: {e}")
        return False


# Test 2: Check for undefined variables in the llm_node function
def test_llm_node_code():
    """
    Analyze the llm_node function for undefined variables.
    This specifically checks for the system_prompt bug.
    """
    print("\nTest 2: Checking llm_node for undefined variables...")
    
    import inspect
    from app.agent.graph.compiler import AgentCompiler
    from app.agent.graph.schema import AgentNode, NodeType
    
    compiler = AgentCompiler(tenant_id=None, db=None)
    
    # Create a test LLM node
    test_node = AgentNode(
        id="test_llm_node",
        type=NodeType.LLM,
        position={"x": 0, "y": 0},
        config={"model_id": "test-model"}
    )
    
    # Build the node function
    node_fn = compiler._build_node_fn(test_node)
    
    # Get the source code of the returned function
    try:
        source = inspect.getsource(node_fn)
        print(f"  Node function source code captured ({len(source)} chars)")
        
        # Check if 'system_prompt' is used
        if 'system_prompt' in source:
            # Check if it's properly assigned
            import ast
            tree = ast.parse(source, mode='exec')
            
            # Find all Name nodes where 'system_prompt' is used
            undefined = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == 'system_prompt':
                    if isinstance(node.ctx, ast.Load):
                        print("  ✗ Found 'system_prompt' usage without definition!")
                        undefined = True
                        break
            
            if undefined:
                print("  → BUG CONFIRMED: 'system_prompt' is used but not defined in llm_node")
                return False
        else:
            print("  ✓ No 'system_prompt' usage found (or it's properly scoped)")
            return True
            
    except Exception as e:
        # getsource might fail for closures, so let's try a different approach
        print(f"  Note: Could not get source directly: {e}")
        print("  Trying execution test instead...")
        return None


# Test 3: Actually execute the llm_node to trigger the error
async def test_llm_node_execution():
    """
    Try to execute an LLM node to see if it throws NameError for system_prompt.
    Since we're testing without a real DB, it should hit the mock path or error.
    """
    print("\nTest 3: Testing llm_node execution...")
    
    from app.agent.graph.compiler import AgentCompiler
    from app.agent.graph.schema import AgentNode, NodeType
    
    # Create compiler without DB/tenant (will use mock path)
    compiler = AgentCompiler(tenant_id=None, db=None)
    
    # Create a test LLM node
    test_node = AgentNode(
        id="test_llm_node",
        type=NodeType.LLM,
        position={"x": 0, "y": 0},
        config={"model_id": "test-model"}
    )
    
    # Build and execute the node function
    node_fn = compiler._build_node_fn(test_node)
    
    # Prepare mock state
    mock_state = {
        "messages": [{"role": "user", "content": "Hello"}],
        "steps": []
    }
    
    try:
        # Execute node - if it hits the mock path, we won't see the bug
        # We need to test with db/tenant_id to trigger the real LLM path
        result = await node_fn(mock_state)
        print(f"  ✓ Node executed successfully (mock path)")
        print(f"  Result: {result}")
        return True  # Mock path worked, but bug might still exist in real path
    except NameError as e:
        print(f"  ✗ NameError caught: {e}")
        if "system_prompt" in str(e):
            print("  → BUG CONFIRMED: 'system_prompt' is not defined")
        return False
    except Exception as e:
        print(f"  ✗ Other error: {type(e).__name__}: {e}")
        return False


# Test 4: Check the actual source file for the bug
def test_source_file_for_bug():
    """
    Read the compiler source file and check for the undefined system_prompt bug.
    """
    print("\nTest 4: Checking source file for undefined variable bug...")
    
    compiler_path = "/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/graph/compiler.py"
    
    with open(compiler_path, 'r') as f:
        source = f.read()
        lines = source.split('\n')
    
    # Find the llm_node function and check for system_prompt
    in_llm_node = False
    system_prompt_defined = False
    system_prompt_used_line = None
    
    for i, line in enumerate(lines, 1):
        if 'async def llm_node' in line:
            in_llm_node = True
            continue
        
        if in_llm_node:
            # Check if we've exited the function
            if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                # Assuming 8-space indentation for nested functions
                if 'async def' in line or 'def' in line:
                    break
            
            # Check for assignment of system_prompt
            if 'system_prompt' in line and '=' in line and 'system_prompt=' not in line:
                # Check if it's an assignment (not a kwarg)
                if line.strip().startswith('system_prompt'):
                    system_prompt_defined = True
                    print(f"  Found system_prompt definition at line {i}: {line.strip()}")
            
            # Check for usage of system_prompt
            if 'system_prompt=system_prompt' in line:
                system_prompt_used_line = i
                print(f"  Found system_prompt usage at line {i}: {line.strip()}")
    
    if system_prompt_used_line and not system_prompt_defined:
        print(f"\n  ✗ BUG CONFIRMED!")
        print(f"  The variable 'system_prompt' is used at line {system_prompt_used_line} but never defined in llm_node.")
        print(f"  This will cause a NameError when the LLM node executes with a real database connection.")
        return False
    elif system_prompt_defined:
        print("  ✓ system_prompt is properly defined before use")
        return True
    else:
        print("  ? Could not determine, manual inspection recommended")
        return None


async def main():
    print("=" * 60)
    print("Agent Execution Bug Test Script")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Compiler imports", test_compiler_imports()))
    results.append(("Source file bug check", test_source_file_for_bug()))
    results.append(("LLM node execution", await test_llm_node_execution()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL" if result is False else "? UNKNOWN"
        print(f"  {name}: {status}")
    
    # Conclusion
    print("\n" + "-" * 60)
    print("Conclusion:")
    print("-" * 60)
    
    bug_confirmed = any(r[1] is False for r in results if "bug check" in r[0].lower())
    if bug_confirmed:
        print("""
The bug has been confirmed:
In backend/app/agent/graph/compiler.py, the `llm_node` function uses 
`system_prompt=system_prompt` at line ~192, but the variable `system_prompt` 
is never defined within that function scope.

This causes a NameError when the agent tries to execute an LLM node, which:
1. Silently fails in the streaming endpoint
2. Sends an empty response to the frontend
3. Results in the user seeing an empty AI response

FIX: Define `system_prompt` in the llm_node function, or extract it from 
the node config (node.config.get('system_prompt', None)).
        """)
    
    return not bug_confirmed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
