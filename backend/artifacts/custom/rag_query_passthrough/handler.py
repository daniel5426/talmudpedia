def execute(context):
    """Return the input query with an added metadata tag."""
    query = context.input_data or {}
    if isinstance(query, str):
        query = {"text": query}
    if not isinstance(query, dict):
        query = {"value": query}

    tag = context.config.get("tag", "passthrough")
    metadata = dict(query.get("metadata") or {})
    metadata["tag"] = tag
    query["metadata"] = metadata
    return query
