import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock

from app.rag.pipeline.operator_executor import (
    ExecutorRegistry,
    OperatorInput,
    ExecutionContext,
    LoaderExecutor,
    ChunkerExecutor,
    EmbedderExecutor,
    StorageExecutor,
    PassthroughExecutor
)
from app.rag.pipeline.registry import OperatorSpec, DataType, OperatorCategory

@pytest.mark.asyncio
async def test_passthrough_executor():
    spec = OperatorSpec(
        operator_id="passthrough",
        display_name="Passthrough",
        category=OperatorCategory.NORMALIZATION,
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.RAW_DOCUMENTS
    )
    executor = PassthroughExecutor(spec)
    input_data = OperatorInput(data="hello", metadata={"test": True})
    context = ExecutionContext(step_id="step1")
    
    output = await executor.execute(input_data, context)
    assert output.success
    assert output.data == "hello"
    assert output.metadata == {"test": True}

@pytest.mark.asyncio
async def test_executor_registry_fail_fast():
    spec = OperatorSpec(
        operator_id="non_existent_op",
        display_name="Non Existent",
        category=OperatorCategory.NORMALIZATION,
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.RAW_DOCUMENTS
    )
    
    with pytest.raises(ValueError, match="No executor implementation found for operator: non_existent_op"):
        ExecutorRegistry.create_executor(spec)

@pytest.mark.asyncio
async def test_loader_executor_local(monkeypatch):
    spec = OperatorSpec(
        operator_id="local_loader",
        display_name="Local Loader",
        category=OperatorCategory.SOURCE,
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS
    )
    
    mock_loader = AsyncMock()
    mock_loader.load.return_value = [{"text": "doc1", "metadata": {}}, {"text": "doc2", "metadata": {}}]
    
    mock_create_loader = MagicMock(return_value=mock_loader)
    monkeypatch.setattr("app.rag.factory.RAGFactory.create_loader", mock_create_loader)
    
    executor = LoaderExecutor(spec)
    # Source node gets input params in data
    input_data = OperatorInput(data={"base_path": "/test"})
    context = ExecutionContext(step_id="step1", config={"base_path": "/test"})
    
    output = await executor.execute(input_data, context)
    assert output.success
    assert len(output.data) == 2
    assert output.data[0]["text"] == "doc1"
    
    mock_create_loader.assert_called_once()

@pytest.mark.asyncio
async def test_chunker_executor_recursive(monkeypatch):
    spec = OperatorSpec(
        operator_id="recursive_chunker",
        display_name="Recursive Chunker",
        category=OperatorCategory.CHUNKING,
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.CHUNKS
    )
    
    mock_chunk = MagicMock()
    mock_chunk.model_dump.return_value = {"text": "chunk1", "metadata": {}}
    
    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = [mock_chunk]
    
    mock_create_chunker = MagicMock(return_value=mock_chunker)
    monkeypatch.setattr("app.rag.factory.RAGFactory.create_chunker", mock_create_chunker)
    
    executor = ChunkerExecutor(spec)
    input_data = OperatorInput(data=[{"text": "long text", "id": "doc1"}])
    context = ExecutionContext(step_id="step2", config={"chunk_size": 100})
    
    output = await executor.execute(input_data, context)
    assert output.success
    assert len(output.data) == 1
    assert output.data[0]["text"] == "chunk1"

@pytest.mark.asyncio
async def test_embedder_executor(monkeypatch):
    spec = OperatorSpec(
        operator_id="model_embedder",
        display_name="Model Embedder",
        category=OperatorCategory.EMBEDDING,
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS
    )
    
    mock_embedder = AsyncMock()
    mock_result = MagicMock()
    mock_result.values = [0.1, 0.2]
    mock_embedder.embed_batch.return_value = [mock_result]
    
    mock_resolver = MagicMock()
    mock_resolver.resolve_embedding = AsyncMock(return_value=mock_embedder)
    
    mock_resolver_class = MagicMock(return_value=mock_resolver)
    monkeypatch.setattr("app.services.model_resolver.ModelResolver", mock_resolver_class)
    
    executor = EmbedderExecutor(spec)
    input_data = OperatorInput(data=[{"text": "chunk1"}])
    
    # Mock context with DB
    context = ExecutionContext(
        step_id="step3", 
        config={"model_id": "test_model"},
        tenant_id=str(uuid.uuid4())
    )
    context.db = MagicMock() # Mock DB session
    
    output = await executor.execute(input_data, context)
    assert output.success
    assert output.data[0]["values"] == [0.1, 0.2]

@pytest.mark.asyncio
async def test_storage_executor_pinecone(monkeypatch):
    spec = OperatorSpec(
        operator_id="pinecone_store",
        display_name="Pinecone Store",
        category=OperatorCategory.STORAGE,
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.NONE
    )
    
    mock_vector_store = AsyncMock()
    mock_vector_store.upsert.return_value = 1
    
    mock_create_vs = MagicMock(return_value=mock_vector_store)
    monkeypatch.setattr("app.rag.factory.RAGFactory.create_vector_store", mock_create_vs)
    
    executor = StorageExecutor(spec)
    input_data = OperatorInput(data=[{"text": "chunk1", "values": [0.1, 0.2], "id": "c1"}])
    context = ExecutionContext(step_id="step4", config={"index_name": "test-index", "provider": "pinecone"})
    
    output = await executor.execute(input_data, context)
    assert output.success
    assert output.data["upsert_count"] == 1
    
    mock_vector_store.upsert.assert_awaited_once()
