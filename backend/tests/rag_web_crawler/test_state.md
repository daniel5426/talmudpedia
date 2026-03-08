# RAG Web Crawler Tests

Last Updated: 2026-03-08

## Scope
Execution and provider coverage for the `web_crawler` source operator backed by self-hosted Crawl4AI.

## Test Files
- `backend/tests/rag_web_crawler/test_crawl4ai_provider.py`
- `backend/tests/rag_web_crawler/test_web_crawler_executor.py`

## Key Scenarios Covered
- Crawl4AI auth header is omitted by default and included when configured.
- Crawl4AI polling handles job submission fallback, result normalization, timeouts, and connection failures.
- Crawl4AI payload building covers the small set of node-level crawl controls exposed by the operator.
- `web_crawler` runtime inputs override saved node config for a run, including content mode and page-level crawl controls.
- The executor registry resolves `web_crawler` to a built-in executor.
- Invalid or missing `start_urls` and invalid `content_preference` fail with explicit validation errors.

## Last Run
- Command: `PYTHONPATH=backend pytest -q backend/tests/rag_web_crawler`
- Date: 2026-03-08 18:16 EET
- Result: Pass (11 passed)

## Known Gaps / Follow-ups
- Add a live integration smoke test against a local Crawl4AI container when a stable dev endpoint is available.
- Add coverage for provider-managed robots/stealth options if those become part of the operator contract.
