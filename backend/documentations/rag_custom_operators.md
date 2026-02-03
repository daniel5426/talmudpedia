# Custom Operators Feature

The Custom Operators feature provides a dedicated interface for creating, testing, and managing Python-based operators for RAG pipelines. This allows for deep customization of data transformation logic while maintaining the safety and isolation of the core engine.

## Overview

Custom operators allow users to inject custom logic into RAG pipelines. These operators execute Python code and can transform data at various stages (ingestion, chunking, embedding, etc.). They adhere to a strict input/output contract based on the `DataType` system, including the new `QUERY` and `RETRIEVAL_RESULT` types.

## Execution Protocol

Custom operators support two execution protocols. The **Modern Protocol** is recommended for all new operators.

### 1. Modern Protocol (Recommended)
The operator defines an `execute` function that receives a single `context` object.

```python
def execute(context):
    """
    Args:
        context: An object containing:
            - input_data: The list of items from the previous node.
            - config: Dictionary of configuration parameters.
            - metadata: Global execution metadata.
    
    Returns:
        A list of processed items.
    """
    items = context.input_data
    config = context.config
    
    # Logic here
    result = [item.upper() if isinstance(item, str) else item for item in items]
    
    return result
```

### 2. Legacy Protocol
For backward compatibility, the operator can define a `process` function.

```python
def process(input_data, config):
    """
    Args:
        input_data: The list of items from the previous node.
        config: Dictionary of configuration parameters.
    
    Returns:
        A list of processed items.
    """
    return input_data
```

## User Interface

The management interface is located at `/admin/rag/operators`.

### 1. Operators List
A dashboard showing all available custom operators with their key metadata (Slug, Category, Types, Version).

### 2. Operator Editor
A high-performance IDE environment featuring:
- **Monaco Code Editor**: Full-featured code editor with syntax highlighting and automatic template generation.
- **Floating Config Bubble**: Manage operator metadata (Display Name, Slug, Category, Input/Output Types).
- **Test Console (NEW)**: A built-in terminal-like panel at the bottom to verify code logic immediately.
    - **Input Tab**: Provide custom JSON input data.
    - **Config Tab**: Provide custom JSON configuration.
    - **Output Tab**: Real-time view of results, execution time, and full Python stack traces on failure.

## Testing Operators

The "Run Test" feature allows developers to validate their code without running a full pipeline.
1. Click the **Play** button in the top toolbar or the **Terminal** icon in the footer.
2. Define your test payload in the **Input** tab.
3. Click **Run Test**.
4. Review the results in the **Output** tab. Success is marked by an emerald badge; failures show the exact line number and error message from the Python interpreter.

## Security & Sanboxing

Custom code runs in a highly restricted execution environment:
- **Available Builtins**: `len`, `range`, `enumerate`, `zip`, `map`, `filter`, `list`, `dict`, `set`, `tuple`, `str`, `int`, `float`, `bool`, `print`, `isinstance`, `sorted`, `min`, `max`, `sum`, `any`, `all`, `abs`, `round`.
- **Available Libraries**: `re`, `json`, `datetime`.
- **Restrictions**: File system access, network requests, and importing arbitrary modules are blocked for security and tenant isolation.

## Integration

- **Sidebar**: Accessible via "RAG Management > Operators".
- **Pipeline Builder**: Custom operators appear in the "Custom" category of the node catalog. The "New Operator" link inside the builder redirects here for rapid creation.
- **Type Safety**: Connections in the Visual Pipeline Builder are validated against the `Input Type` and `Output Type` defined in the operator configuration.

## Technical Details

- **Frontend**: Next.js, Shadcn/UI, Monaco Editor.
- **Backend Execution**: `PythonOperatorExecutor` uses safe `exec` with a restricted namespace and handles execution in a thread pool to prevent blocking the main API.
- **Storage**: Multi-tenant PostgreSQL with version tracking.
