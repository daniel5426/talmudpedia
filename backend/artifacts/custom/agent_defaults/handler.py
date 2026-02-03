def execute(state, config, context):
    inputs = context.get("inputs") or {}
    current_context = dict(state.get("context") or {})
    current_context.update({
        "static_value": inputs.get("static_value"),
        "count_hint": inputs.get("count_hint"),
        "feature_flag": inputs.get("feature_flag"),
    })
    return {
        "context": current_context,
        "transform_output": {
            "static_value": inputs.get("static_value"),
            "count_hint": inputs.get("count_hint"),
            "feature_flag": inputs.get("feature_flag"),
        }
    }
