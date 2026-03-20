# LangChain v1 / LangGraph Modernization

Last Updated: 2026-03-20

## Summary
- Hard-cut removed legacy chat workflow files: `advanced_rag`, `simple_rag`, the legacy `/chat` bootstrap router, and their old factory/config glue.
- Pinned the maintained LangChain/LangGraph provider stack to a known-compatible matrix used by the backend runtime.
- Kept the maintained architecture centered on `ModelResolver`, `LLMProviderAdapter`, `ReasoningNodeExecutor`, `LangGraphAdapter`, and the platform event emitter.

## Pinned Dependency Matrix
- `langgraph==1.0.4`
- `langchain-core==1.2.20`
- `langchain-openai==1.1.0`
- `langchain-anthropic==1.4.0`
- `langchain-google-genai==4.2.1`

## Migration Notes
- The maintained runtime no longer supports the deleted legacy chat bootstrap path.
- `LLMProviderAdapter` remains the normalization boundary for provider stream chunks entering LangChain/LangGraph execution.
- The custom tool loop and runtime adapter remain the canonical execution path; this migration does not adopt LangChain `create_agent`.

## Regression Focus
- Provider chunk normalization and final-response aggregation
- Tool-call chunk handling in the reasoning loop
- Durable checkpoint persistence and LangGraph runtime execution
