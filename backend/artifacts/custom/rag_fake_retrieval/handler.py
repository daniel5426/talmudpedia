def execute(context):
    """Return fake search results based on the query text."""
    query = context.input_data or {}
    if isinstance(query, str):
        query = {"text": query}
    if not isinstance(query, dict):
        query = {"value": query}

    text = query.get("text") or query.get("value") or ""
    count = context.config.get("result_count", 2)
    source = context.config.get("source", "fake")

    results = []
    for idx in range(int(count)):
        results.append({
            "id": f"{source}-{idx}",
            "text": f"{text}-result-{idx}",
            "score": 1.0 - (idx * 0.1),
            "metadata": {"source": source}
        })
    return results
