import pytest

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
        self.events.append(("start", node_id, node_type))

    def emit_node_end(self, node_id, name, node_type, output_data=None):
        self.events.append(("end", node_id, node_type))

    def emit_error(self, error, node_id=None):
        self.events.append(("error", node_id, error))


def _patch_resolver(monkeypatch, response_text: str):
    async def fake_resolve(self, model_id):
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
