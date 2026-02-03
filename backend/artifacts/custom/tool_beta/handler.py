def execute(state, config, context):
    inputs = context.get("inputs") or {}
    number = inputs.get("number", 1)
    multiplier = inputs.get("multiplier", 2)
    try:
        result = int(number) * int(multiplier)
    except Exception:
        result = 0

    current_context = dict(state.get("context") or {})
    current_context["tool_beta"] = result

    return {
        "context": current_context,
        "tool_outputs": [{"tool_beta": result}]
    }
