# Adding New Operators (Code Artifacts)

This guide explains how to add new logic to the platform using the **Code Artifacts** system. Artifacts are file-based operators that can be used in RAG Pipelines, Agent Graphs, and as Tools.

---

## 1. Creating a New Artifact

The preferred way to add logic is by creating an artifact in `backend/artifacts/`.

### Step A: Scaffold the Directory
Use the CLI helper to create a standard structure:
```bash
python3 backend/scripts/create_artifact.py my_awesome_operator --scope agent
```

### Step B: Define the Manifest (`artifact.yaml`)
Define your operator's contract. The **Field Mapping Architecture** allows you to specify explicit inputs and outputs.

```yaml
id: my_awesome_operator
display_name: Awesome Operator
version: 1.0.0
category: transform
scope: agent  # or rag

# Explicit Input Schema (Enables Field Mapping in UI)
inputs:
  - name: query
    type: string
    required: true
    description: "The text to process"
  - name: max_length
    type: number
    default: 100

# Output Schema
outputs:
  - name: result
    type: string

# Traditional Configuration (Static settings)
config:
  - name: api_key
    type: string
    required: false
```

### Step C: Implement the Handler (`handler.py`)
Implement the execution logic. The `exec_context` now contains a resolved `inputs` dictionary.

```python
async def execute(state: dict, config: dict, exec_context: dict) -> dict:
    # 1. Access resolved inputs (mapped from UI)
    query = exec_context["inputs"].get("query")
    
    # 2. Access static config
    api_key = config.get("api_key")
    
    # 3. Process
    processed_text = await my_logic(query, api_key)
    
    # 4. Return updates to merge into Agent State
    return {
        "processed_result": processed_text
    }
```

---

## 2. Using Field Mapping in the Agent Builder

When you add an artifact node to the Agent Builder, you can map its inputs using **Expressions**:

- **Direct State Access**: `{{ messages[-1].content }}`
- **Upstream Connection**: `{{ upstream.previous_node_id.output_field }}`
- **String Interpolation**: `Translate this: {{ text_to_translate }}`

---

## 3. Traditional (Built-in) Operators

For core platform operators that are hardcoded in the engine, follow the legacy process of adding to `backend/app/rag/pipeline/registry.py` and `operator_executor.py`. However, **Code Artifacts are recommended for 95% of use cases.**

---

## Summary Checklist
- [ ] Created artifact directory in `backend/artifacts/`
- [ ] Defined `inputs` and `outputs` in `artifact.yaml`
- [ ] Implemented `execute` in `handler.py`
- [ ] Added unit tests in `tests/`
- [ ] (Frontend) Verified custom icon and mapping UI in the Agent Builder
