import json
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import ValidationError

from .published_apps_admin_builder_core import (
    _builder_compile_error,
    _extract_http_error_details,
    _select_builder_context_paths,
    _truncate_for_context,
)
from .published_apps_admin_builder_patch import _apply_patch_operations, _sanitize_prompt_text
from .published_apps_admin_shared import (
    BUILDER_MODEL_MAX_RETRIES,
    BUILDER_MODEL_NAME,
    BuilderModelPatchPlan,
    BuilderPatchGenerationResult,
)

def _build_builder_context_snapshot(
    files: Dict[str, str],
    entry_file: str,
    user_prompt: str,
    *,
    recent_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    selected_paths = _select_builder_context_paths(
        files,
        entry_file,
        user_prompt,
        recent_paths=recent_paths,
    )
    selected_files = [
        {"path": path, "content": _truncate_for_context(files[path])}
        for path in selected_paths
    ]
    return {
        "entry_file": entry_file,
        "file_count": len(files),
        "selected_paths": selected_paths,
        "selected_files": selected_files,
    }


def _extract_openai_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    fragments: List[str] = []
    output_items = getattr(response, "output", None)
    if not isinstance(output_items, list):
        return ""

    for item in output_items:
        content_items = getattr(item, "content", None)
        if content_items is None and isinstance(item, dict):
            content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for part in content_items:
            part_type = getattr(part, "type", None)
            if part_type is None and isinstance(part, dict):
                part_type = part.get("type")
            if part_type not in {"output_text", "text"}:
                continue
            text_value = getattr(part, "text", None)
            if text_value is None and isinstance(part, dict):
                text_value = part.get("text") or part.get("value")
            if text_value:
                fragments.append(str(text_value))
    return "".join(fragments).strip()


async def _request_builder_model_patch_plan(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    repair_feedback: List[str],
    recent_paths: Optional[List[str]] = None,
) -> BuilderModelPatchPlan:
    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for model-backed builder patch generation")

    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("openai package is required for model-backed builder patch generation") from exc

    context_snapshot = _build_builder_context_snapshot(
        files,
        entry_file,
        user_prompt,
        recent_paths=recent_paths,
    )
    model_input = {
        "task": user_prompt,
        "contract": {
            "operations": "BuilderPatchOp[]",
            "summary": "short user-facing summary",
            "rationale": "concise implementation rationale",
            "assumptions": "list of assumptions",
        },
        "repair_feedback": repair_feedback[-4:],
        "context": context_snapshot,
    }
    system_prompt = (
        "You generate safe frontend patch operations.\n"
        "Return only strict JSON (no markdown) with keys: operations, summary, rationale, assumptions.\n"
        "Each operation must be one of: upsert_file, delete_file, rename_file, set_entry_file.\n"
        "Use paths under src/, public/, or allowed Vite root files only."
    )

    client = AsyncOpenAI(api_key=openai_api_key)
    response = await client.responses.create(
        model=BUILDER_MODEL_NAME,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(model_input)},
        ],
        max_output_tokens=1400,
    )
    raw_text = _extract_openai_response_text(response)
    if not raw_text:
        raise RuntimeError("Model returned an empty patch response")

    try:
        return BuilderModelPatchPlan.model_validate_json(raw_text)
    except ValidationError as exc:
        raise ValueError(f"Model output failed schema validation: {exc}") from exc


async def _generate_builder_patch_with_model(
    *,
    user_prompt: str,
    files: Dict[str, str],
    entry_file: str,
    repair_feedback: Optional[List[str]] = None,
    recent_paths: Optional[List[str]] = None,
) -> BuilderPatchGenerationResult:
    feedback = list(repair_feedback or [])
    last_errors: List[Dict[str, str]] = []

    for _ in range(BUILDER_MODEL_MAX_RETRIES + 1):
        try:
            patch_plan = await _request_builder_model_patch_plan(
                user_prompt=user_prompt,
                files=files,
                entry_file=entry_file,
                repair_feedback=feedback,
                recent_paths=recent_paths,
            )
        except (RuntimeError, ValueError) as exc:
            message = str(exc)
            feedback.append(message)
            last_errors.append({"message": message})
            continue

        if not patch_plan.operations:
            message = "Model returned zero operations"
            feedback.append(message)
            last_errors.append({"message": message})
            continue

        try:
            _apply_patch_operations(files, entry_file, patch_plan.operations)
        except HTTPException as exc:
            message, diagnostics = _extract_http_error_details(exc)
            feedback.append(message)
            last_errors.extend(diagnostics)
            continue

        summary = _sanitize_prompt_text(patch_plan.summary, 180) or "prepared a draft update"
        rationale = _sanitize_prompt_text(patch_plan.rationale, 400)
        assumptions = [
            _sanitize_prompt_text(item, 180)
            for item in patch_plan.assumptions
            if _sanitize_prompt_text(item, 180)
        ]
        return BuilderPatchGenerationResult(
            operations=patch_plan.operations,
            summary=summary,
            rationale=rationale,
            assumptions=assumptions,
        )

    raise _builder_compile_error(
        "Model patch generation failed",
        diagnostics=last_errors[-6:] or [{"message": "Model output could not be validated"}],
    )
