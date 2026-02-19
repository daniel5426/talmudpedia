from __future__ import annotations

from typing import Iterable


def _normalize_messages(messages: Iterable[dict[str, str]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def build_opencode_effective_prompt(
    *,
    current_user_prompt: str,
    messages: list[dict[str, str]] | None,
    max_chars: int,
) -> str:
    budget = max(1024, int(max_chars or 0))
    prompt = str(current_user_prompt or "").strip()

    normalized = _normalize_messages(messages)
    if prompt and (not normalized or normalized[-1]["role"] != "user" or normalized[-1]["content"] != prompt):
        normalized.append({"role": "user", "content": prompt})

    if not normalized:
        return prompt or "Continue."

    selected: list[dict[str, str]] = []
    used = 0
    for item in reversed(normalized):
        role_label = "User" if item["role"] == "user" else "Assistant"
        line = f"{role_label}: {item['content']}"
        if selected and used + len(line) > budget:
            break
        selected.append(item)
        used += len(line)
    selected.reverse()

    if not selected:
        return prompt or "Continue."

    if prompt:
        current = prompt
        if selected[-1]["role"] == "user" and selected[-1]["content"] == prompt:
            history_items = selected[:-1]
        else:
            history_items = selected
    else:
        last = selected[-1]
        if last["role"] == "user":
            current = last["content"]
            history_items = selected[:-1]
        else:
            current = "Continue."
            history_items = selected

    lines: list[str] = []
    if history_items:
        lines.append("Conversation context:")
        for item in history_items:
            role_label = "User" if item["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {item['content']}")
        lines.append("")
    lines.append("Current user request:")
    lines.append(current)
    return "\n".join(lines).strip()
