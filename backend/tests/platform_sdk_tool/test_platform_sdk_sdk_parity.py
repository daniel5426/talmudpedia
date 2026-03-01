from artifacts.builtin.platform_sdk import handler


class _FakeArtifactsAPI:
    def __init__(self):
        self.calls = []

    def list(self, tenant_slug=None):
        self.calls.append({"method": "list", "tenant_slug": tenant_slug})
        return {"data": [{"id": "artifact-1"}]}

    def get(self, artifact_id, tenant_slug=None):
        self.calls.append({"method": "get", "artifact_id": artifact_id, "tenant_slug": tenant_slug})
        return {"data": {"id": artifact_id}}

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

    def delete(self, artifact_id, tenant_slug=None, options=None):
        self.calls.append(
            {
                "method": "delete",
                "artifact_id": artifact_id,
                "tenant_slug": tenant_slug,
                "options": options,
            }
        )
        return {"data": {"deleted": True, "artifact_id": artifact_id}}


class _FakeToolsAPI:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append({"method": "list", "kwargs": kwargs})
        return {"data": [{"id": "tool-1"}]}

    def get(self, tool_id):
        self.calls.append({"method": "get", "tool_id": tool_id})
        return {"data": {"id": tool_id}}

    def create(self, spec, options=None):
        self.calls.append({"method": "create", "spec": spec, "options": options})
        return {"data": {"id": "tool-1"}}

    def update(self, tool_id, patch, options=None):
        self.calls.append({"method": "update", "tool_id": tool_id, "patch": patch, "options": options})
        return {"data": {"id": tool_id, "updated": True}}

    def publish(self, tool_id, options=None):
        self.calls.append({"method": "publish", "tool_id": tool_id, "options": options})
        return {"data": {"id": tool_id, "published": True}}

    def create_version(self, tool_id, new_version, options=None):
        self.calls.append({"method": "create_version", "tool_id": tool_id, "new_version": new_version, "options": options})
        return {"data": {"id": tool_id, "version": new_version}}

    def delete(self, tool_id, options=None):
        self.calls.append({"method": "delete", "tool_id": tool_id, "options": options})
        return {"data": {"deleted": True, "tool_id": tool_id}}


class _FakeAgentsAPI:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append({"method": "list", "kwargs": kwargs})
        return {"data": {"agents": [{"id": "agent-1", "slug": "demo-agent"}]}}

    def get(self, agent_id):
        self.calls.append({"method": "get", "agent_id": agent_id})
        return {"data": {"id": agent_id}}

    def create(self, spec, options=None):
        self.calls.append({"method": "create", "spec": spec, "options": options})
        return {"data": {"id": "agent-created"}}

    def update(self, agent_id, patch, method="PATCH", options=None):
        self.calls.append({"method": "update", "agent_id": agent_id, "patch": patch, "http_method": method, "options": options})
        return {"data": {"id": agent_id, "updated": True}}

    def publish(self, agent_id, options=None):
        self.calls.append({"method": "publish", "agent_id": agent_id, "options": options})
        return {"data": {"id": agent_id, "published": True}}

    def validate(self, agent_id, payload=None):
        self.calls.append({"method": "validate", "agent_id": agent_id, "payload": payload})
        return {"data": {"valid": True}}

    def execute(self, agent_id, payload):
        self.calls.append({"method": "execute", "agent_id": agent_id, "payload": payload})
        return {"data": {"run_id": "run-1", "output": {"text": "ok"}}}

    def start_run(self, agent_id, payload):
        self.calls.append({"method": "start_run", "agent_id": agent_id, "payload": payload})
        return {"data": {"run_id": "run-started"}}

    def resume_run(self, run_id, payload):
        self.calls.append({"method": "resume_run", "run_id": run_id, "payload": payload})
        return {"data": {"run_id": run_id, "status": "running"}}

    def get_run(self, run_id, include_tree=False):
        self.calls.append({"method": "get_run", "run_id": run_id, "include_tree": include_tree})
        return {"data": {"run_id": run_id, "status": "completed"}}

    def get_run_tree(self, run_id):
        self.calls.append({"method": "get_run_tree", "run_id": run_id})
        return {"data": {"run_id": run_id, "nodes": []}}


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


class _FakeRagAPI:
    def __init__(self):
        self.calls = []

    def create_job(self, executable_pipeline_id, input_params, tenant_slug, options=None):
        self.calls.append(
            {
                "method": "create_job",
                "executable_pipeline_id": executable_pipeline_id,
                "input_params": input_params,
                "tenant_slug": tenant_slug,
                "options": options,
            }
        )
        return {"data": {"id": "job-1"}}


class _FakeModelsAPI:
    def __init__(self):
        self.calls = []

    def update_provider(self, model_id, provider_id, patch, options=None):
        self.calls.append(
            {
                "method": "update_provider",
                "model_id": model_id,
                "provider_id": provider_id,
                "patch": patch,
                "options": options,
            }
        )
        return {"data": {"id": provider_id, "updated": True}}


class _FakeCredentialsAPI:
    def __init__(self):
        self.calls = []

    def delete(self, credential_id, force_disconnect=False, options=None):
        self.calls.append(
            {
                "method": "delete",
                "credential_id": credential_id,
                "force_disconnect": force_disconnect,
                "options": options,
            }
        )
        return {"data": {"id": credential_id, "deleted": True}}


class _FakeKnowledgeStoresAPI:
    def __init__(self):
        self.calls = []

    def list(self, tenant_slug):
        self.calls.append({"method": "list", "tenant_slug": tenant_slug})
        return {"data": [{"id": "store-1"}]}


class _FakeAuthAPI:
    def __init__(self):
        self.calls = []

    def mint_workload_token(self, payload):
        self.calls.append({"method": "mint_workload_token", "payload": payload})
        return {"data": {"access_token": "delegated-token"}}


class _FakeWorkloadSecurityAPI:
    def __init__(self):
        self.calls = []

    def decide_action_approval(self, payload):
        self.calls.append({"method": "decide_action_approval", "payload": payload})
        return {"data": {"status": "approved"}}


class _FakeControlClient:
    def __init__(self):
        self.artifacts = _FakeArtifactsAPI()
        self.tools = _FakeToolsAPI()
        self.agents = _FakeAgentsAPI()
        self.orchestration = _FakeOrchestrationAPI()
        self.catalog = _FakeCatalogAPI()
        self.rag = _FakeRagAPI()
        self.models = _FakeModelsAPI()
        self.credentials = _FakeCredentialsAPI()
        self.knowledge_stores = _FakeKnowledgeStoresAPI()
        self.auth = _FakeAuthAPI()
        self.workload_security = _FakeWorkloadSecurityAPI()


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


def test_tools_publish_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "tools.publish",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"tool_id": "tool-22"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "tool-22", "published": True}
    call = fake.tools.calls[0]
    assert call["method"] == "publish"
    assert call["tool_id"] == "tool-22"


def test_artifacts_delete_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "artifacts.delete",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"artifact_id": "artifact-7"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"deleted": True, "artifact_id": "artifact-7"}
    call = fake.artifacts.calls[0]
    assert call["method"] == "delete"
    assert call["artifact_id"] == "artifact-7"


def test_agents_start_run_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.start_run",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"agent_id": "agent-1", "run": {"input": {"text": "hello"}}},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"run_id": "run-started"}
    call = fake.agents.calls[0]
    assert call["method"] == "start_run"
    assert call["agent_id"] == "agent-1"
    assert call["payload"] == {"input": {"text": "hello"}}


def test_agents_get_run_tree_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.get_run_tree",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {"run_id": "run-1"},
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"run_id": "run-1", "nodes": []}
    call = fake.agents.calls[0]
    assert call["method"] == "get_run_tree"
    assert call["run_id"] == "run-1"


def test_rag_create_job_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "rag.create_job",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "executable_pipeline_id": "exec-1",
                    "tenant_slug": "tenant-a",
                    "input_params": {"query": "hello"},
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "job-1"}
    call = fake.rag.calls[0]
    assert call["method"] == "create_job"
    assert call["executable_pipeline_id"] == "exec-1"
    assert call["tenant_slug"] == "tenant-a"


def test_models_update_provider_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "models.update_provider",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "model_id": "model-1",
                    "provider_id": "provider-1",
                    "patch": {"priority": 2},
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "provider-1", "updated": True}
    call = fake.models.calls[0]
    assert call["method"] == "update_provider"
    assert call["model_id"] == "model-1"
    assert call["provider_id"] == "provider-1"


def test_credentials_delete_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "credentials.delete",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "credential_id": "cred-1",
                    "force_disconnect": True,
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"id": "cred-1", "deleted": True}
    call = fake.credentials.calls[0]
    assert call["method"] == "delete"
    assert call["force_disconnect"] is True


def test_knowledge_stores_list_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "knowledge_stores.list",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "tenant_slug": "tenant-a",
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == [{"id": "store-1"}]
    call = fake.knowledge_stores.calls[0]
    assert call["method"] == "list"
    assert call["tenant_slug"] == "tenant-a"


def test_auth_mint_workload_token_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "auth.mint_workload_token",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "subject_type": "user",
                    "subject_id": "user-1",
                    "scope_subset": ["tools.write"],
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"access_token": "delegated-token"}
    call = fake.auth.calls[0]
    assert call["method"] == "mint_workload_token"
    assert call["payload"]["subject_id"] == "user-1"


def test_workload_security_decide_approval_contract_parity(monkeypatch):
    _patch_auth(monkeypatch)
    fake = _FakeControlClient()
    monkeypatch.setattr(handler, "_control_client", lambda _client: fake)

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "workload_security.decide_approval",
                "tenant_id": "tenant-1",
                "token": "token",
                "payload": {
                    "subject_type": "tool",
                    "subject_id": "tool-1",
                    "action_scope": "tools.delete",
                    "status": "approved",
                },
            }
        },
    )

    assert out["context"]["errors"] == []
    assert out["context"]["result"] == {"status": "approved"}
    call = fake.workload_security.calls[0]
    assert call["method"] == "decide_action_approval"
    assert call["payload"]["action_scope"] == "tools.delete"
