# Test State: HITL User Approval

**Scope**
Human input approval/rejection behavior and gating for pause/resume paths.

**Test Files**
- `test_hitl_user_approval.py`

**Scenarios Covered**
- `user_approval` can_execute gating
- Approve/reject branch resolution
- Invalid approval payload handling
- Legacy `human_input` input/message acceptance

**Last Run**
- Command: `TEST_USE_REAL_DB=0 pytest -q`
- Date: 2026-02-04 16:59 EET
- Result: Pass

**Known Gaps / Follow-ups**
- No end-to-end resume flow or interrupt checkpoint integration test
