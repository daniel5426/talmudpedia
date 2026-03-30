import pytest
from langchain_core.messages import AIMessageChunk

from app.agent.core.llm_adapter import LLMProviderAdapter, extract_usage_payload_from_message
from app.agent.executors.standard import ReasoningNodeExecutor
from app.agent.execution.tool_input_contracts import ToolSchemaValidationError


class _FakeProvider:
    def __init__(self, responses):
        self._responses = responses

    async def stream(self, _messages, system_prompt=None, **_kwargs):
        for chunk in self._responses:
            yield chunk


class _RawToolCallMessage:
    def __init__(self):
        self.content = ""
        self.tool_calls = [{"name": "web_search", "args": {"query": "gemini"}}]
        self.tool_call_chunks = []
        self.additional_kwargs = {}
        self.response_metadata = {}


@pytest.mark.asyncio
async def test_llm_provider_adapter_stream_normalizes_content_blocks():
    provider = _FakeProvider(
        [
            AIMessageChunk(
                content_blocks=[
                    {"type": "reasoning", "reasoning": "plan"},
                    {
                        "type": "text",
                        "text": "hello",
                        "annotations": [
                            {
                                "type": "citation",
                                "url": "https://example.com",
                                "title": "Example",
                            }
                        ],
                    },
                    {
                        "type": "tool_call_chunk",
                        "id": "call-1",
                        "name": "web_search",
                        "args": '{"query":"gemini"}',
                        "index": 0,
                    },
                    {
                        "type": "server_tool_result",
                        "id": "server-1",
                        "name": "web_search",
                        "output": {"result": "ok"},
                    },
                ]
            )
        ]
    )

    adapter = LLMProviderAdapter(provider)
    chunks = [chunk async for chunk in adapter._astream([])]

    assert len(chunks) == 1
    message = chunks[0].message
    assert message.content == "hello"
    assert message.additional_kwargs["reasoning_content"] == "plan"
    assert message.additional_kwargs["citations"] == [
        {"type": "citation", "url": "https://example.com", "title": "Example"}
    ]
    assert message.additional_kwargs["server_tool_results"][0]["name"] == "web_search"
    assert len(message.tool_call_chunks) == 1
    assert message.tool_call_chunks[0]["id"] == "call-1"
    assert message.tool_call_chunks[0]["name"] == "web_search"
    assert message.tool_call_chunks[0]["args"] == '{"query":"gemini"}'
    assert message.tool_call_chunks[0]["index"] == 0


@pytest.mark.asyncio
async def test_llm_provider_adapter_ainvoke_preserves_reasoning_and_tool_calls():
    provider = _FakeProvider(
        [
            AIMessageChunk(
                content_blocks=[
                    {"type": "reasoning", "reasoning": "think"},
                    {"type": "text", "text": "done"},
                    {
                        "type": "tool_call",
                        "id": "call-1",
                        "name": "web_search",
                        "args": {"query": "gemini"},
                    },
                ]
            )
        ]
    )

    adapter = LLMProviderAdapter(provider)
    response = await adapter.ainvoke([])

    assert response.content == "done"
    assert response.additional_kwargs["reasoning_content"] == "think"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["id"] == "call-1"
    assert response.tool_calls[0]["name"] == "web_search"
    assert response.tool_calls[0]["args"] == {"query": "gemini"}


@pytest.mark.asyncio
async def test_llm_provider_adapter_ainvoke_aggregates_stream_usage_metadata():
    provider = _FakeProvider(
        [
            AIMessageChunk(
                content_blocks=[{"type": "text", "text": "Hello"}],
                usage_metadata={"input_tokens": 2, "output_tokens": 66, "total_tokens": 68},
            ),
            AIMessageChunk(
                content_blocks=[{"type": "text", "text": " world"}],
                usage_metadata={"input_tokens": 0, "output_tokens": 8, "total_tokens": 8},
            ),
        ]
    )

    adapter = LLMProviderAdapter(provider)
    response = await adapter.ainvoke([])

    assert response.content == "Hello world"
    assert extract_usage_payload_from_message(response) == {
        "input_tokens": 2,
        "output_tokens": 74,
        "total_tokens": 76,
    }


def test_extract_usage_payload_from_message_supports_gemini_usage_metadata():
    message = AIMessageChunk(
        content="done",
        response_metadata={
            "usage_metadata": {
                "prompt_token_count": 120,
                "candidates_token_count": 45,
                "total_token_count": 165,
                "thoughts_token_count": 12,
            }
        },
    )

    assert extract_usage_payload_from_message(message) == {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "reasoning_tokens": 12,
    }


def test_build_langchain_tool_rejects_null_property_schema():
    executor = ReasoningNodeExecutor(tenant_id=None, db=None)
    tool = type(
        "Tool",
        (),
        {
            "slug": "broken-tool",
            "name": "Broken Tool",
            "description": "broken",
            "schema": {
                "input": {
                    "type": "object",
                    "properties": {"deal_id": None},
                    "required": ["deal_id"],
                }
            },
        },
    )()

    with pytest.raises(ToolSchemaValidationError) as exc:
        executor._build_langchain_tool(tool)

    assert exc.value.tool_name == "broken-tool"
    assert exc.value.schema_path == "input.properties.deal_id"


@pytest.mark.asyncio
async def test_llm_provider_adapter_adds_missing_tool_call_id():
    provider = _FakeProvider([_RawToolCallMessage()])

    adapter = LLMProviderAdapter(provider)
    chunks = [chunk async for chunk in adapter._astream([])]

    assert len(chunks) == 1
    assert chunks[0].message.tool_calls == [
        {"name": "web_search", "args": {"query": "gemini"}, "id": None, "type": "tool_call"}
    ]


def test_build_langchain_tool_builds_nested_args_schema():
    executor = ReasoningNodeExecutor(tenant_id=None, db=None)
    tool = type(
        "Tool",
        (),
        {
            "slug": "write-record",
            "name": "Write Record",
            "description": "writes a record",
            "schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "deal_id": {"type": "string"},
                        "payload": {
                            "type": "object",
                            "properties": {
                                "client_id": {"type": "string"},
                                "flags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["client_id"],
                        },
                    },
                    "required": ["deal_id", "payload"],
                }
            },
        },
    )()

    langchain_tool = executor._build_langchain_tool(tool)
    parsed = langchain_tool.args_schema(
        deal_id="deal-1",
        payload={"client_id": "client-1", "flags": ["urgent"]},
    )

    assert parsed.deal_id == "deal-1"
    assert parsed.payload.client_id == "client-1"
    assert parsed.payload.flags == ["urgent"]
