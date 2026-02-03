def execute(state, config, context):
    inputs = context.get("inputs") or {}
    prefix = config.get("prefix", "echo:")

    user_text = inputs.get("user_text")
    upstream_note = inputs.get("upstream_note")
    tagged = inputs.get("tagged")
    if tagged is None:
        tagged = inputs.get("default_tag", "default-tag")

    echo = f"{prefix} {user_text}" if user_text is not None else f"{prefix}"

    current_context = dict(state.get("context") or {})
    current_context.update({
        "echo": echo,
        "note": upstream_note,
        "tagged": tagged,
    })

    return {
        "context": current_context,
        "transform_output": {
            "echo": echo,
            "note": upstream_note,
            "tagged": tagged,
        }
    }
