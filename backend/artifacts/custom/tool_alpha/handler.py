def execute(state, config, context):
    inputs = context.get("inputs") or {}
    text = inputs.get("text")
    suffix = inputs.get("suffix", "!")
    result = f"{text}{suffix}" if text is not None else suffix

    current_context = dict(state.get("context") or {})
    current_context["tool_alpha"] = result

    return {
        "context": current_context,
        "tool_outputs": [{"tool_alpha": result}]
    }
