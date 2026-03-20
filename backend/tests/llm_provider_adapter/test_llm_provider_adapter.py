from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agent.core.llm_adapter import LLMProviderAdapter


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    async def stream(self, messages, system_prompt=None, **kwargs):
        for chunk in self.responses:
            yield chunk


@pytest.mark.asyncio
async def test_astream_normalizes_non_string_chunk_content_and_preserves_tool_chunks():
    tool_call_chunks = [{"id": "call-1", "name": "search", "args": "{\"q\":\"latest\"}", "index": 0}]
    provider = FakeProvider(
        [
            AIMessageChunk(
                content=[{"text": "hello"}, {"text": " world"}],
                tool_call_chunks=tool_call_chunks,
            )
        ]
    )
    adapter = LLMProviderAdapter(provider)

    chunks = [chunk async for chunk in adapter._astream([HumanMessage(content="hi")])]

    assert len(chunks) == 1
    assert chunks[0].message.content == "hello world"
    assert len(chunks[0].message.tool_call_chunks) == 1
    assert chunks[0].message.tool_call_chunks[0]["id"] == "call-1"
    assert chunks[0].message.tool_call_chunks[0]["name"] == "search"
    assert chunks[0].message.tool_call_chunks[0]["args"] == '{"q":"latest"}'


@pytest.mark.asyncio
async def test_ainvoke_aggregates_raw_provider_delta_formats():
    provider = FakeProvider(
        [
            "Hello",
            SimpleNamespace(type="response.output_text.delta", delta=" world"),
            SimpleNamespace(type="response.reasoning_text.delta", delta="private-thought"),
        ]
    )
    adapter = LLMProviderAdapter(provider)

    response = await adapter.ainvoke([HumanMessage(content="hi")])

    assert response.content == "Hello world"


@pytest.mark.asyncio
async def test_astream_captures_reasoning_content_in_additional_kwargs():
    provider = FakeProvider(
        [
            SimpleNamespace(type="response.reasoning_text.delta", delta="think"),
        ]
    )
    adapter = LLMProviderAdapter(provider)

    chunks = [chunk async for chunk in adapter._astream([HumanMessage(content="hi")])]

    assert len(chunks) == 1
    assert chunks[0].message.content == ""
    assert chunks[0].message.additional_kwargs["reasoning_content"] == "think"
