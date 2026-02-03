# scripts/test_sdk.py
import sys
import os
# Add the project root (parent of backend) to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.sdk import Client, Pipeline

def test_rag_creation():
    print("--- Testing SDK RAG Pipeline Creation ---")
    
    # 1. Connect
    # Assuming running locally without auth or with a dev token if needed
    client = Client(base_url="http://localhost:8000")
    
    # 2. Inspect Nodes
    print("RAG Nodes Available:", list(client.nodes.categories.keys()))
    
    # 2.5 Create a Custom Artifact (SaaS Style)
    print("--- Creating Custom Artifact via API ---")
    from backend.sdk import ArtifactBuilder
    
    code = """
from app.rag.pipeline.operator_executor import OperatorInput, OperatorOutput

def run(input_data: OperatorInput, config: dict) -> OperatorOutput:
    return OperatorOutput(success=True, data={"result": "processed by custom code"})
"""
    try:
        ArtifactBuilder.create(
            client,
            name="sdk_test_node",
            display_name="SDK Test Node",
            python_code=code,
            input_type="raw_documents",
            output_type="normalized_documents"
        )
        print("Artifact created successfully.")
    except Exception as e:
        print(f"Artifact creation failed (might already exist): {e}")

    # Reconnect to pick up the new node
    client.connect()
    
    # 3. Create Nodes
    # Using 'LocalLoader' from 'source' category
    # Note: If 'source' category is empty/missing in local dev without data, strict access might fail
    # We'll try to use the custom node we just made if possible, or fallbacks
    
    # Check if 'custom' category exists now
    if hasattr(client.nodes, "custom"):
        print("Found custom nodes:", client.nodes.custom._node_classes.keys())
        custom_node = client.nodes.custom.SdkTestNode()
        print("Instantiated Custom Node:", custom_node)
    
    try:
        loader = client.nodes.source.LocalLoader(
            base_path="/tmp/test_docs",
            file_extensions=".txt"
        )
    except AttributeError:
        # Fallback if specific node not loaded in dev env
        print("LocalLoader not found, skipping specific node test")
        return

    # Using 'TokenBasedChunker' from 'chunking' category
    try:
        chunker = client.nodes.chunking.TokenBasedChunker(
            chunk_size=500
        )
    except AttributeError:
        print("TokenBasedChunker not found")
        return
    
    # 4. Build Pipeline
    pipe = Pipeline("SDK Test Pipeline", "Created via Dynamic SDK")
    pipe.add(loader, chunker)
    if 'custom_node' in locals():
        pipe.add(custom_node)
        pipe.connect(chunker, custom_node)
    else:
        pipe.connect(loader, chunker)
    
    print("Pipeline Payload:", pipe.to_payload())
    
    # 5. Submit (This might fail if auth is required, but we test payload generation mainly)
    try:
        # We need a tenant slug if the user requires it? 
        # The SDK client currently doesn't handle tenant headers automatically unless we add them
        # Let's see if we can just print the payload for now to verify "offline" creation
        # or try to hit it
        # client.headers["X-Tenant-Slug"] = "default" # Example
        pass
    except Exception as e:
        print(f"Submission Error: {e}")

if __name__ == "__main__":
    test_rag_creation()
