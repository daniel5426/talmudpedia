import pytest

from app.services.context_window_service import ContextWindowService
from app.services.model_limits_service import ModelLimitsService
from app.services.prompt_snapshot_service import PromptSnapshotService
from app.services.token_counter_service import TokenCounterService


@pytest.mark.asyncio
async def test_google_token_counter_uses_provider_count_api(monkeypatch):
    captured = {}

    class _FakeModels:
        def count_tokens(self, *, model, contents, config=None):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return type("Resp", (), {"total_tokens": 321})()

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = _FakeModels()

    monkeypatch.setattr("app.services.token_counter_service.genai.Client", _FakeClient)

    snapshot = PromptSnapshotService.build_from_langchain(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt="Be helpful",
        tools=[],
        extra_context={},
    )
    tokens, source = await TokenCounterService().count_input_tokens(
        provider="google",
        provider_model_id="gemini-3-flash-preview",
        snapshot=snapshot,
        api_key="google-key",
    )

    assert tokens == 321
    assert source == "provider_count_api"
    assert captured["model"] == "gemini-3-flash-preview"
    assert captured["config"] is None
    assert captured["contents"][0]["parts"][0]["text"] == "Be helpful"


@pytest.mark.asyncio
async def test_anthropic_token_counter_uses_provider_count_api(monkeypatch):
    captured = {}

    class _FakeMessages:
        async def count_tokens(self, **kwargs):
            captured.update(kwargs)
            return type("Resp", (), {"input_tokens": 403})()

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.messages = _FakeMessages()

    monkeypatch.setattr("app.services.token_counter_service.AsyncAnthropic", _FakeClient)

    snapshot = PromptSnapshotService.build_from_langchain(
        messages=[{"role": "user", "content": "What is the weather?"}],
        system_prompt="You are a scientist",
        tools=[
            {
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
            }
        ],
        extra_context={},
    )
    tokens, source = await TokenCounterService().count_input_tokens(
        provider="anthropic",
        provider_model_id="claude-opus-4-6",
        snapshot=snapshot,
        api_key="anthropic-key",
    )

    assert tokens == 403
    assert source == "provider_count_api"
    assert captured["model"] == "claude-opus-4-6"
    assert captured["system"] == "You are a scientist"
    assert captured["tools"][0]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_token_counter_falls_back_to_tiktoken_without_provider_api(monkeypatch):
    class _Encoding:
        def encode(self, value):
            return list(range(len(value.split())))

    monkeypatch.setattr("app.services.token_counter_service.tiktoken.encoding_for_model", lambda _model: _Encoding())

    snapshot = PromptSnapshotService.build_from_langchain(
        messages=[{"role": "user", "content": "hello there"}],
        system_prompt=None,
        tools=[],
        extra_context={},
    )
    tokens, source = await TokenCounterService().count_input_tokens(
        provider="xai",
        provider_model_id="grok-4.20-reasoning",
        snapshot=snapshot,
    )

    assert tokens is not None
    assert source == "tokenizer_estimate"


@pytest.mark.asyncio
async def test_model_limits_service_prefers_provider_model_info(monkeypatch):
    class _FakeModels:
        def get(self, *, model, config=None):
            assert model == "models/gemini-3-flash-preview"
            return type("Resp", (), {"input_token_limit": 999_999})()

    class _FakeClient:
        def __init__(self, api_key):
            self.models = _FakeModels()

    monkeypatch.setattr("app.services.model_limits_service.genai.Client", _FakeClient)

    limit, source = await ModelLimitsService(db=None).resolve_input_limit(
        organization_id=None,
        model_id="google/gemini-3-flash-preview",
        resolved_provider="google",
        resolved_provider_model_id="gemini-3-flash-preview",
        api_key="google-key",
    )

    assert limit == 999_999
    assert source == "provider_model_info"


@pytest.mark.asyncio
async def test_context_window_pre_run_uses_token_counter_and_model_limits(monkeypatch):
    async def _fake_count_input_tokens(self, **kwargs):
        return 1234, "provider_count_api"

    async def _fake_resolve_input_limit(self, **kwargs):
        return 200000, "provider_model_info"

    monkeypatch.setattr(TokenCounterService, "count_input_tokens", _fake_count_input_tokens)
    monkeypatch.setattr(ModelLimitsService, "resolve_input_limit", _fake_resolve_input_limit)

    window = await ContextWindowService(db=None).build_pre_run_window(
        organization_id=None,
        model_id="some-model",
        resolved_provider="google",
        resolved_provider_model_id="gemini-3-flash-preview",
        api_key="google-key",
        input_params={"messages": [{"role": "user", "content": "hi"}]},
        runtime_context={},
    )

    assert window["source"] == "provider_count_api"
    assert window["max_tokens"] == 200000
    assert window["max_tokens_source"] == "provider_model_info"
    assert window["input_tokens"] == 1234
