import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.executors.classify_executor import ClassifyNodeExecutor
from app.agent.execution.emitter import active_emitter
from app.services.model_resolver import ModelResolver


class FakeProvider:
    def __init__(self, response_text: str):
        self.response_text = response_text

    async def stream(self, messages, system_prompt=None, **kwargs):
        yield self.response_text


class FakeEmitter:
    def __init__(self):
        self.events = []

    def emit_node_start(self, node_id, name, node_type, input_data=None):
        self.events.append(("start", node_id, node_type, input_data))

    def emit_node_end(self, node_id, name, node_type, output_data=None):
        self.events.append(("end", node_id, node_type, output_data))

    def emit_error(self, error, node_id=None):
        self.events.append(("error", node_id, error))


def _patch_resolver(monkeypatch, response_text: str):
    async def fake_resolve(self, model_id, **kwargs):
        return FakeProvider(response_text)

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)


@pytest.mark.asyncio
async def test_classify_executor_validates_config():
    executor = ClassifyNodeExecutor(tenant_id=None, db=None)

    result = await executor.validate_config({})
    assert result.valid is False

    result = await executor.validate_config({"model_id": "model-1", "categories": [{"name": "A"}]})
    assert result.valid is False


@pytest.mark.asyncio
async def test_classify_executor_case_insensitive_match(monkeypatch):
    _patch_resolver(monkeypatch, "alpha")

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    token = active_emitter.set(FakeEmitter())
    try:
        result = await executor.execute(
            {"messages": [{"role": "user", "content": "hi"}]},
            {
                "model_id": "model-1",
                "categories": [{"name": "Alpha"}, {"name": "Beta"}],
            },
            {"node_id": "classify-1"},
        )
    finally:
        active_emitter.reset(token)

    assert result["branch_taken"] == "Alpha"
    assert result["next"] == "Alpha"


@pytest.mark.asyncio
async def test_classify_executor_defaults_to_else(monkeypatch):
    _patch_resolver(monkeypatch, "Unknown")

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "categories": [{"name": "Alpha"}, {"name": "Beta"}],
        },
        {"node_id": "classify-2"},
    )

    assert result["branch_taken"] == "else"
    assert result["next"] == "else"


@pytest.mark.asyncio
async def test_classify_emits_start_and_end(monkeypatch):
    _patch_resolver(monkeypatch, "Alpha")

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    fake_emitter = FakeEmitter()
    token = active_emitter.set(fake_emitter)
    try:
        await executor.execute(
            {"messages": [{"role": "user", "content": "hi"}]},
            {
                "model_id": "model-1",
                "categories": [{"name": "Alpha"}, {"name": "Beta"}],
            },
            {"node_id": "classify-3"},
        )
    finally:
        active_emitter.reset(token)

    event_types = [e[0] for e in fake_emitter.events]
    assert "start" in event_types
    assert "end" in event_types
    end_event = next(event for event in fake_emitter.events if event[0] == "end")
    assert end_event[3]["selected"] == "Alpha"
    assert end_event[3]["branch_label"] == "Alpha"
    assert end_event[3]["branch_id"] == "Alpha"
    assert end_event[3]["classification_result"] == "Alpha"


@pytest.mark.asyncio
async def test_classify_executor_accepts_content_block_response(monkeypatch):
    class BlockProvider:
        async def stream(self, messages, system_prompt=None, **kwargs):
            yield AIMessageChunk(content_blocks=[{"type": "text", "text": "Beta"}])

    async def fake_resolve(self, model_id, **kwargs):
        return BlockProvider()

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "categories": [{"name": "Alpha"}, {"name": "Beta"}],
        },
        {"node_id": "classify-4"},
    )

    assert result["branch_taken"] == "Beta"


@pytest.mark.asyncio
async def test_classify_executor_prefers_workflow_input_text(monkeypatch):
    class RecordingProvider:
        def __init__(self):
            self.messages = None

        async def stream(self, messages, system_prompt=None, **kwargs):
            self.messages = messages
            yield "Alpha"

    provider = RecordingProvider()

    async def fake_resolve(self, model_id, **kwargs):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    await executor.execute(
        {
            "workflow_input": {"text": "route this payment request"},
            "messages": [{"role": "user", "content": "ignored history"}],
        },
        {
            "model_id": "model-1",
            "categories": [{"name": "Alpha"}, {"name": "Beta"}],
        },
        {"node_id": "classify-5"},
    )

    assert provider.messages is not None
    assert len(provider.messages) == 2
    assert provider.messages[1].content == "route this payment request"


@pytest.mark.asyncio
async def test_classify_executor_routes_with_stable_category_id(monkeypatch):
    _patch_resolver(monkeypatch, "Support")

    executor = ClassifyNodeExecutor(tenant_id=None, db=None)
    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "categories": [
                {"id": "cat_support", "name": "Support"},
                {"id": "cat_sales", "name": "Sales"},
            ],
        },
        {"node_id": "classify-6"},
    )

    assert result["category"] == "Support"
    assert result["branch_label"] == "Support"
    assert result["branch_id"] == "cat_support"
    assert result["branch_taken"] == "cat_support"
    assert result["next"] == "cat_support"
