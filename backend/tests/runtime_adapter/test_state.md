# Test State: Runtime Adapter Layer

Last Updated: 2026-04-05

**Scope**
GraphIR → runtime adapter compilation and execution plumbing, runtime registry behavior, node factory fallback, and platform event emission via the adapter.

**Test Files**
- `test_runtime_adapter_layer.py`

**Scenarios Covered**
- Default adapter selection and custom adapter registration
- LangGraph adapter compile/run/stream for minimal graph
- LangGraph adapter cancels the underlying graph task when the stream consumer is cancelled
- Platform event emission from a node executor
- Node factory behavior when executor is missing
- Durable checkpointer persistence across saver reloads

**Last Run**
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/runtime_adapter`
- Date: 2026-04-05 Asia/Hebron
- Result: pass (`6 passed`)

**Known Gaps / Follow-ups**
- No coverage for multi-runtime adapters beyond a dummy stub
