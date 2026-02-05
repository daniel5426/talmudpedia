# Test State: Runtime Adapter Layer

**Scope**
GraphIR → runtime adapter compilation and execution plumbing, runtime registry behavior, node factory fallback, and platform event emission via the adapter.

**Test Files**
- `test_runtime_adapter_layer.py`

**Scenarios Covered**
- Default adapter selection and custom adapter registration
- LangGraph adapter compile/run/stream for minimal graph
- Platform event emission from a node executor
- Node factory behavior when executor is missing

**Last Run**
- Command: `TEST_USE_REAL_DB=0 pytest -q`
- Date: 2026-02-04 16:59 EET
- Result: Pass

**Known Gaps / Follow-ups**
- No coverage for persistent checkpointers or multi-runtime adapters beyond a dummy stub
