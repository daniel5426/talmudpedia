from types import SimpleNamespace

from app.agent.executors.standard import ReasoningNodeExecutor


def _make_executor() -> ReasoningNodeExecutor:
    return ReasoningNodeExecutor(tenant_id=None, db=None)


def test_tool_call_chunk_buffer_merges_dict_fragments() -> None:
    executor = _make_executor()
    buffers = {}
    order = []
    message = SimpleNamespace(
        tool_call_chunks=[
            {
                "id": "call-1",
                "name": "write_file",
                "args": {"path": "src/App.tsx"},
                "index": 0,
            },
            {
                "id": "call-1",
                "args": {"content": "export const App = () => <div/>;"},
                "index": 0,
            },
        ]
    )

    executor._buffer_tool_call_chunks(message, buffers, order)
    calls = executor._finalize_tool_calls(buffers, order)

    assert len(calls) == 1
    assert calls[0]["name"] == "write_file"
    assert calls[0]["args"]["path"] == "src/App.tsx"
    assert calls[0]["args"]["content"] == "export const App = () => <div/>;"


def test_tool_call_chunk_finalize_prefers_fallback_on_parse_failure() -> None:
    executor = _make_executor()
    buffers = {
        "call-1": {
            "id": "call-1",
            "name": "write_file",
            "args_text": '{"path":"src/App.tsx"{"content":"broken"}',
            "args_obj": {},
            "index": 0,
        }
    }
    order = ["call-1"]
    fallback_calls = [
        {
            "id": "call-1",
            "name": "write_file",
            "args": {
                "path": "src/App.tsx",
                "content": "export const App = () => <main/>;",
            },
        }
    ]

    calls = executor._finalize_tool_calls(buffers, order, fallback_calls=fallback_calls)

    assert calls == fallback_calls


def test_normalize_tool_call_keeps_direct_input_fields_when_wrappers_absent() -> None:
    executor = _make_executor()
    payload = {
        "tool": "write_file",
        "path": "src/App.tsx",
        "content": "export const App = () => <div/>;",
    }

    normalized = executor._normalize_tool_call(payload)

    assert normalized is not None
    assert normalized["tool_name"] == "write_file"
    assert normalized["input"]["path"] == "src/App.tsx"
    assert normalized["input"]["content"] == "export const App = () => <div/>;"
