import asyncio
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = str(Path(__file__).parent.parent)
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Set environment variables from user input

from app.rag.pipeline.operator_executor import ExecutorRegistry, OperatorInput, ExecutionContext
from app.rag.pipeline.registry import OperatorRegistry, OperatorSpec, OperatorCategory, DataType

async def test_recreation():
    # 1. Setup Registry
    registry = OperatorRegistry.get_instance()
    
    # 2. Define Custom Sefaria Operator
    with open("/Users/danielbenassaya/.gemini/antigravity/brain/fbd225cf-3511-4ea4-836d-b64c7a91fe0c/sefaria_operator.py", "r") as f:
        sefaria_code = f.read()
        
    sefaria_spec = OperatorSpec(
        operator_id="sefaria_source",
        display_name="Sefaria Source",
        category=OperatorCategory.CUSTOM,
        description="Fetches text from Sefaria",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        is_custom=True,
        python_code=sefaria_code,
        version="1.0.0"
    )
    
    # 3. Execution Context
    ctx = ExecutionContext(
        tenant_id="test-tenant",
        pipeline_id="test-pipeline",
        job_id="test-job",
        step_id="step1",
        config={"index_title": "Mishnah Berakhot", "limit": 5}
    )
    
    print("--- Testing Sefaria Source Operator ---")
    executor = ExecutorRegistry.create_executor(sefaria_spec, sefaria_code)
    out1 = await executor.safe_execute(OperatorInput(data=None), ctx)
    print(f"Success: {out1.success}")
    if out1.success:
        print(f"Fetched {len(out1.data)} segments")
    else:
        print(f"Error: {out1.error_message}")
        return

    # 4. Testing Build-in Chunker
    print("\n--- Testing Built-in Recursive Chunker ---")
    chunker_spec = registry.get("recursive_chunker")
    if not chunker_spec:
        print("recursive_chunker not found in registry")
    else:
        chunker_ctx = ExecutionContext(
            tenant_id="test-tenant",
            pipeline_id="test-pipeline",
            job_id="test-job",
            step_id="step2",
            config={"chunk_size": 1000, "chunk_overlap": 100}
        )
        chunker_executor = ExecutorRegistry.create_executor(chunker_spec)
        out2 = await chunker_executor.safe_execute(OperatorInput(data=out1.data), chunker_ctx)
        print(f"Success: {out2.success}")
        if out2.success:
            print(f"Created {len(out2.data)} chunks")
        else:
            print(f"Error: {out2.error_message}")
            return

    # 5. Testing Model Embedder
    print("\n--- Testing Model Embedder (Gemini) ---")
    embedder_spec = registry.get("model_embedder")
    if not embedder_spec:
        print("model_embedder not found in registry")
    else:
        embedder_ctx = ExecutionContext(
            tenant_id="test-tenant",
            pipeline_id="test-pipeline",
            job_id="test-job",
            step_id="step3",
            config={"model_id": "gemini-embedding-001"} 
        )
        embedder_executor = ExecutorRegistry.create_executor(embedder_spec)
        out3 = await embedder_executor.safe_execute(OperatorInput(data=out2.data), embedder_ctx)
        print(f"Success: {out3.success}")
        if out3.success:
            print(f"Generated embeddings for {len(out3.data)} chunks")
        else:
            print(f"Error: {out3.error_message}")
            return

    # 6. Testing Pinecone Store
    print("\n--- Testing Pinecone Store ---")
    store_spec = registry.get("pinecone_store")
    if not store_spec:
        print("pinecone_store not found in registry")
    else:
        store_ctx = ExecutionContext(
            tenant_id="test-tenant",
            pipeline_id="test-pipeline",
            job_id="test-job",
            step_id="step4",
            config={"index_name": "talmudpedia"} 
        )
        store_executor = ExecutorRegistry.create_executor(store_spec)
        out4 = await store_executor.safe_execute(OperatorInput(data=out3.data, metadata=out3.metadata), store_ctx)
        print(f"Success: {out4.success}")
        if out4.success:
            print(f"Stored {len(out3.data)} vectors in Pinecone")
        else:
            print(f"Error: {out4.error_message}")

if __name__ == "__main__":
    asyncio.run(test_recreation())
