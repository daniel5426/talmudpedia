from app.services import registry_seeding


def test_platform_architect_graph_is_single_agent_topology():
    graph = registry_seeding._build_architect_graph_definition(
        model_id="model-1",
        tool_ids=["tool-a", "tool-b", "tool-c", "tool-d"],
    )
    node_types = {node.get("type") for node in graph.get("nodes", [])}
    assert node_types == {"start", "agent", "end"}

    node_ids = {node.get("id") for node in graph.get("nodes", [])}
    assert "architect_runtime" in node_ids
    assert "spawn_catalog_stage" not in node_ids
    assert "join_catalog_stage" not in node_ids
    runtime_node = next(node for node in graph["nodes"] if node["id"] == "architect_runtime")
    assert runtime_node["config"]["tools"] == ["tool-a", "tool-b", "tool-c", "tool-d"]
    instructions = runtime_node["config"]["instructions"]
    assert "Never call architect.run" in instructions
    assert "one tool call at a time" in instructions
    assert "Draft-first is mandatory" in instructions
    assert "Never ask the user for tenant_id" in instructions
    assert "machine-readable JSON report" not in instructions
    assert "output_format" not in runtime_node["config"]
    assert "output_schema" not in runtime_node["config"]


def test_platform_architect_domain_tool_specs_are_seeded():
    slugs = set(registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS.keys())
    assert slugs == {
        "platform-rag",
        "platform-agents",
        "platform-assets",
        "platform-governance",
    }
    assert "architect.run" not in registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-agents"]["actions"]


def test_platform_domain_schema_is_action_specific_one_of():
    agents_spec = registry_seeding.PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-agents"]
    schema = registry_seeding._build_platform_domain_tool_schema("platform-agents", agents_spec)
    input_schema = schema["input"]
    variants = input_schema["oneOf"]
    by_action = {variant["properties"]["action"]["const"]: variant for variant in variants}

    assert "agents.create" in by_action
    assert "agents.nodes.catalog" in by_action
    assert "agents.nodes.schema" in by_action
    assert "agents.nodes.validate" in by_action
    assert "agents.publish" in by_action
    assert "architect.run" not in by_action
    assert "x-action-contract" in by_action["agents.create"]
    assert "idempotency_key" not in by_action["agents.create"]["required"]
    assert "request_metadata" not in by_action["agents.create"]["required"]
    assert "tenant_id" not in by_action["agents.create"]["required"]
    assert "node_types" in by_action["agents.nodes.schema"]["properties"]["payload"]["required"]
    assert "idempotency_key" not in by_action["agents.nodes.catalog"]["required"]
    assert "idempotency_key" not in by_action["agents.get"]["required"]
