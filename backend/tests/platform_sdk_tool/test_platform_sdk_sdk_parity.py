from artifacts.builtin.platform_sdk import handler


class _FakeArtifactsAPI:
    def __init__(self):
        self.calls = []

    def create_draft(self, spec, *, tenant_slug=None, options=None):
        self.calls.append({"method": "create_draft", "spec": spec, "tenant_slug": tenant_slug, "options": options})
        return {"data": {"id": "draft-1"}}

    def update_draft(self, artifact_id, patch, *, tenant_slug=None, options=None):
        self.calls.append(
            {
                "method": "update_draft",
                "artifact_id": artifact_id,
                "patch": patch,
                "tenant_slug": tenant_slug,
                "options": options,
            }
        )
        return {"data": {"id": artifact_id, "updated": True}}


class _FakeToolsAPI:
    def __init__(self):
        self.calls = []

    def create(self, spec, options=None):
        self.calls.append({"method": "create", "spec": spec, "options": options})
        return {"data": {"id": "tool-1"}}

    def update(self, tool_id, patch, options=None):
        self.calls.append({"method": "update", "tool_id": tool_id, "patch": patch, "options": options})
        return {"data": {"id": tool_id, "updated": True}}


class _FakeAgentsAPI:
    def __init__(self):
        self.calls = []

    def execute(self, agent_id, payload):
        self.calls.append({"method": "execute", "agent_id": agent_id, "payload": payload})
        return {"data": {"run_id": "run-1", "output": {"text": "ok"}}}


class _FakeOrchestrationAPI:
    def __init__(self):
        self.calls = []

    def spawn_run(self, payload, options=None):
        self.calls.append({"method": "spawn_run", "payload": payload, "options": options})
        return {"data": {"spawned_run_ids": ["child-1"]}}


class _FakeCatalogAPI:
    def __init__(self):
        self.calls = []

    def get_rag_operator_catalog(self, tenant_slug=None):
        self.calls.append({"method": "get_rag_operator_catalog", "tenant_slug": tenant_slug})
        return {"data": {"ingest": [{"operator_id": "ingest.parse"}]}}

    def list_agent_operators(self):
        self.calls.append({"method": "list_agent_operators"})
        return {"data": [{"type": "start", "category": "core"}]}


class _FakeControlClient:
    def __init__(self):
        self.artifacts = _FakeArtifactsAPI()
        self.tools = _FakeToolsAPI()
        self.agents = _FakeAgentsAPI()
        self.orchestration = _FakeOrchestrationAPI()
        self.catalog = _FakeCatalogAPI()


def _patch_auth(monkeypatch):
    monkeypatch.setattr(
        handler,
        "_resolve_auth",
        lambda inputs, payload, state=None, context=None, action=None, required_scopes=None: (
            "http://localhost:8000",
            "token",
            "tenant-1",
            {},
        ),
    )


def test_artifacts_create_or_update_draft_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "artifacts.create_or_update_draft",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"name": "demo", "python_code": "def execute(x, y=None):\n    return x"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "draft-1"}
    call = fake.artifacts.calls[0]
    assert call["method"] == "create_draft"
    assert call["spec"]["name"] == "demo"
    assert call["spec"]["python_code"].startswith("def execute")
    assert call["options"]["dry_run"] is False


def test_artifacts_update_draft_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "artifacts.create_or_update_draft",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"artifact_id": "draft-42", "description": "updated"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "draft-42", "updated": True}
    call = fake.artifacts.calls[0]
    assert call["method"] == "update_draft"
    assert call["artifact_id"] == "draft-42"
    assert call["patch"]["description"] == "updated"


def test_tools_create_or_update_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "tools.create_or_update",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "tool_id": "tool-123",
                    "patch": {"description": "updated description"},
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "tool-123", "updated": True}
    call = fake.tools.calls[0]
    assert call["method"] == "update"
    assert call["tool_id"] == "tool-123"
    assert call["patch"] == {"description": "updated description"}


def test_agents_execute_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.execute",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"agent_id": "agent-1", "input": {"text": "hello"}},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"]["run_id"] == "run-1"
    call = fake.agents.calls[0]
    assert call["method"] == "execute"
    assert call["agent_id"] == "agent-1"
    assert call["payload"]["input"] == "hello"


def test_orchestration_spawn_run_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "orchestration.spawn_run",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "caller_run_id": "run-parent",
                    "target_agent_slug": "agent-a",
                    "scope_subset": ["agents.execute"],
                    "idempotency_key": "idem-1",
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"spawned_run_ids": ["child-1"]}
    call = fake.orchestration.calls[0]
    assert call["method"] == "spawn_run"
    assert call["payload"]["caller_run_id"] == "run-parent"
    assert call["payload"]["idempotency_key"] == "idem-1"
    assert call["options"]["idempotency_key"] == "idem-1"


def test_catalog_list_capabilities_uses_catalog_methods(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={"inputs": {"action": "catalog.list_capabilities", "tenant_id": "tenant-1", "token": "token"}},
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"]["summary"]["rag"]["total"] == 1
    assert out["context"]["result"]["summary"]["agent"]["total"] == 1
    methods = [c["method"] for c in fake.catalog.calls]
    assert methods == ["get_rag_operator_catalog", "list_agent_operators"]
