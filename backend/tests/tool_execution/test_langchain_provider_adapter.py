from app.agent.components.llm.langchain_provider import LangChainProviderAdapter
from app.db.postgres.models.registry import ModelProviderType


def test_langchain_provider_forces_non_v1_output_version(monkeypatch):
    captured: dict[str, object] = {}

    class FakeChatGoogleGenerativeAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import sys
    import types

    fake_module = types.SimpleNamespace(ChatGoogleGenerativeAI=FakeChatGoogleGenerativeAI)
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_module)

    LangChainProviderAdapter(
        provider=ModelProviderType.GEMINI,
        model="gemini-2.5-pro",
        api_key="test-key",
    )

    assert captured["output_version"] == "v0"
