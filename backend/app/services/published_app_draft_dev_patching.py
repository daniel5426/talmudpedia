from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Dict, List


@dataclass(frozen=True)
class UnifiedDiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]


@dataclass(frozen=True)
class UnifiedDiffFile:
    old_path: str
    new_path: str
    hunks: list[UnifiedDiffHunk]


@dataclass(frozen=True)
class PatchFailure:
    path: str
    hunk_index: int
    expected_start_line: int
    reason: str
    actual_context_preview: list[str]
    recommended_refresh: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "hunk_index": self.hunk_index,
            "expected_start_line": self.expected_start_line,
            "reason": self.reason,
            "actual_context_preview": self.actual_context_preview,
            "recommended_refresh": self.recommended_refresh,
        }


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class BeginPatchOperation:
    op: str
    path: str
    lines: list[str]


def _is_dev_null(path: str) -> bool:
    value = str(path or "").strip()
    return value in {"/dev/null", "dev/null"}


def _strip_prefix(path: str, strip: int) -> str:
    value = str(path or "").strip()
    if _is_dev_null(value):
        return "/dev/null"
    cleaned = value.strip('"')
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        parts = cleaned.split("/")
    else:
        parts = cleaned.split("/")
    if strip > 0 and len(parts) > strip:
        parts = parts[strip:]
    return "/".join(part for part in parts if part)


def _parse_header_path(raw_line: str) -> str:
    value = raw_line[4:] if len(raw_line) >= 4 else ""
    value = value.strip()
    if "\t" in value:
        value = value.split("\t", 1)[0]
    return value


def parse_unified_diff(patch: str) -> tuple[list[UnifiedDiffFile], str | None]:
    text = str(patch or "")
    if "GIT binary patch" in text or "Binary files " in text:
        return [], "PATCH_BINARY_NOT_SUPPORTED"
    lines = text.splitlines()
    index = 0
    parsed: list[UnifiedDiffFile] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            parts = line.split(" ")
            old_path = parts[2] if len(parts) > 2 else ""
            new_path = parts[3] if len(parts) > 3 else ""
            index += 1
            while index < len(lines):
                probe = lines[index]
                if probe.startswith("diff --git "):
                    break
                if probe.startswith("--- "):
                    old_path = _parse_header_path(probe)
                    index += 1
                    if index < len(lines) and lines[index].startswith("+++ "):
                        new_path = _parse_header_path(lines[index])
                    break
                if probe.startswith("rename from "):
                    old_path = probe[len("rename from ") :].strip()
                elif probe.startswith("rename to "):
                    new_path = probe[len("rename to ") :].strip()
                elif probe.startswith("new file mode "):
                    old_path = "/dev/null"
                elif probe.startswith("deleted file mode "):
                    new_path = "/dev/null"
                index += 1
            hunks: list[UnifiedDiffHunk] = []
            index = _parse_hunks(lines, index, hunks)
            if hunks:
                parsed.append(UnifiedDiffFile(old_path=old_path, new_path=new_path, hunks=hunks))
            continue
        if line.startswith("--- ") and (index + 1) < len(lines) and lines[index + 1].startswith("+++ "):
            old_path = _parse_header_path(line)
            new_path = _parse_header_path(lines[index + 1])
            index += 2
            hunks: list[UnifiedDiffHunk] = []
            index = _parse_hunks(lines, index, hunks)
            if hunks:
                parsed.append(UnifiedDiffFile(old_path=old_path, new_path=new_path, hunks=hunks))
            continue
        index += 1
    return parsed, None


def _parse_hunks(lines: list[str], index: int, out: list[UnifiedDiffHunk]) -> int:
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git ") or (line.startswith("--- ") and (index + 1) < len(lines) and lines[index + 1].startswith("+++ ")):
            return index
        if not line.startswith("@@ "):
            index += 1
            continue
        match = HUNK_RE.match(line)
        if not match:
            index += 1
            continue
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        index += 1
        hunk_lines: list[str] = []
        while index < len(lines):
            next_line = lines[index]
            if next_line.startswith("@@ "):
                break
            if next_line.startswith("diff --git "):
                break
            if next_line.startswith("--- ") and (index + 1) < len(lines) and lines[index + 1].startswith("+++ "):
                break
            if not next_line:
                hunk_lines.append(" ")
                index += 1
                continue
            prefix = next_line[:1]
            if prefix in {" ", "+", "-", "\\"}:
                hunk_lines.append(next_line)
                index += 1
                continue
            break
        out.append(
            UnifiedDiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=hunk_lines,
            )
        )
    return index


def _context_preview(lines: list[str], start_index: int) -> list[str]:
    lo = max(0, start_index - 2)
    hi = min(len(lines), start_index + 3)
    preview: list[str] = []
    for idx in range(lo, hi):
        preview.append(f"{idx + 1}: {lines[idx]}")
    return preview


def _recommended_refresh(start_line: int, old_count: int) -> dict[str, int]:
    begin = max(1, int(start_line) - 12)
    end = max(begin, int(start_line) + max(int(old_count), 1) + 12)
    return {"start_line": begin, "end_line": end}


def apply_hunks_strict(
    *,
    source: str,
    hunks: list[UnifiedDiffHunk],
    path: str,
) -> tuple[str | None, list[PatchFailure]]:
    source_lines = source.splitlines()
    output: list[str] = []
    cursor = 0
    failures: list[PatchFailure] = []

    for hunk_index, hunk in enumerate(hunks, start=1):
        expected_idx = max(0, hunk.old_start - 1)
        if expected_idx < cursor or expected_idx > len(source_lines):
            failures.append(
                PatchFailure(
                    path=path,
                    hunk_index=hunk_index,
                    expected_start_line=hunk.old_start,
                    reason="invalid_hunk_offset",
                    actual_context_preview=_context_preview(source_lines, min(max(cursor, 0), len(source_lines) - 1 if source_lines else 0)),
                    recommended_refresh=_recommended_refresh(hunk.old_start, hunk.old_count),
                )
            )
            continue

        output.extend(source_lines[cursor:expected_idx])
        src_idx = expected_idx
        for raw in hunk.lines:
            if raw.startswith("\\"):
                continue
            prefix = raw[:1]
            text = raw[1:] if raw else ""
            if prefix == " ":
                if src_idx >= len(source_lines) or source_lines[src_idx] != text:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=hunk_index,
                            expected_start_line=hunk.old_start,
                            reason="context_mismatch",
                            actual_context_preview=_context_preview(source_lines, src_idx),
                            recommended_refresh=_recommended_refresh(hunk.old_start, hunk.old_count),
                        )
                    )
                    break
                output.append(source_lines[src_idx])
                src_idx += 1
            elif prefix == "-":
                if src_idx >= len(source_lines) or source_lines[src_idx] != text:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=hunk_index,
                            expected_start_line=hunk.old_start,
                            reason="deletion_mismatch",
                            actual_context_preview=_context_preview(source_lines, src_idx),
                            recommended_refresh=_recommended_refresh(hunk.old_start, hunk.old_count),
                        )
                    )
                    break
                src_idx += 1
            elif prefix == "+":
                output.append(text)
            else:
                failures.append(
                    PatchFailure(
                        path=path,
                        hunk_index=hunk_index,
                        expected_start_line=hunk.old_start,
                        reason="unsupported_hunk_line",
                        actual_context_preview=_context_preview(source_lines, src_idx),
                        recommended_refresh=_recommended_refresh(hunk.old_start, hunk.old_count),
                    )
                )
                break
        if failures and failures[-1].hunk_index == hunk_index:
            continue
        cursor = src_idx

    if failures:
        return None, failures
    output.extend(source_lines[cursor:])
    return "\n".join(output), []


def normalize_expected_hash(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1]
    return text.lower()


def hash_text(content: str) -> str:
    return sha256((content or "").encode("utf-8")).hexdigest()


def parse_begin_patch_format(patch: str) -> tuple[list[BeginPatchOperation], str | None]:
    text = str(patch or "")
    if "*** Begin Patch" not in text:
        return [], "PATCH_PARSE_FAILED"
    lines = text.splitlines()
    if not lines:
        return [], "PATCH_PARSE_FAILED"
    try:
        begin_idx = next(index for index, line in enumerate(lines) if line.strip() == "*** Begin Patch")
    except StopIteration:
        return [], "PATCH_PARSE_FAILED"

    index = begin_idx + 1
    operations: list[BeginPatchOperation] = []
    current_op: str | None = None
    current_path: str = ""
    current_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.strip() == "*** End Patch":
            if current_op and current_path:
                operations.append(BeginPatchOperation(op=current_op, path=current_path, lines=current_lines))
            return operations, None if operations else "PATCH_PARSE_FAILED"
        if line.startswith("*** Update File: "):
            if current_op and current_path:
                operations.append(BeginPatchOperation(op=current_op, path=current_path, lines=current_lines))
            current_op = "update"
            current_path = line[len("*** Update File: ") :].strip()
            current_lines = []
            index += 1
            continue
        if line.startswith("*** Add File: "):
            if current_op and current_path:
                operations.append(BeginPatchOperation(op=current_op, path=current_path, lines=current_lines))
            current_op = "add"
            current_path = line[len("*** Add File: ") :].strip()
            current_lines = []
            index += 1
            continue
        if line.startswith("*** Delete File: "):
            if current_op and current_path:
                operations.append(BeginPatchOperation(op=current_op, path=current_path, lines=current_lines))
            operations.append(
                BeginPatchOperation(op="delete", path=line[len("*** Delete File: ") :].strip(), lines=[])
            )
            current_op = None
            current_path = ""
            current_lines = []
            index += 1
            continue
        if line.startswith("*** Move to: "):
            return [], "PATCH_MOVE_NOT_SUPPORTED"
        if current_op:
            current_lines.append(line)
        index += 1
    return [], "PATCH_PARSE_FAILED"


def _split_begin_patch_segments(lines: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("@@"):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(line)
    if current:
        segments.append(current)
    return segments


def _find_subsequence(lines: list[str], pattern: list[str], *, start: int = 0) -> int:
    if not pattern:
        return max(0, start)
    max_index = len(lines) - len(pattern)
    for idx in range(max(0, start), max_index + 1):
        if lines[idx : idx + len(pattern)] == pattern:
            return idx
    return -1


def _apply_begin_patch_update(
    *,
    source: str,
    path: str,
    lines: list[str],
) -> tuple[str | None, list[PatchFailure]]:
    working = source.splitlines()
    failures: list[PatchFailure] = []
    cursor = 0
    segments = _split_begin_patch_segments(lines)
    if not segments:
        return source, []
    for seg_index, segment in enumerate(segments, start=1):
        old_lines: list[str] = []
        new_lines: list[str] = []
        for raw in segment:
            if raw.startswith("\\"):
                continue
            if not raw:
                old_lines.append("")
                new_lines.append("")
                continue
            prefix = raw[:1]
            text = raw[1:] if len(raw) > 1 else ""
            if prefix == " ":
                old_lines.append(text)
                new_lines.append(text)
            elif prefix == "-":
                old_lines.append(text)
            elif prefix == "+":
                new_lines.append(text)
            else:
                failures.append(
                    PatchFailure(
                        path=path,
                        hunk_index=seg_index,
                        expected_start_line=max(1, cursor + 1),
                        reason="unsupported_begin_patch_line",
                        actual_context_preview=_context_preview(working, cursor),
                        recommended_refresh=_recommended_refresh(cursor + 1, max(1, len(old_lines))),
                    )
                )
                break
        if failures and failures[-1].hunk_index == seg_index:
            continue

        start_idx = _find_subsequence(working, old_lines, start=cursor)
        if start_idx < 0:
            start_idx = _find_subsequence(working, old_lines, start=0)
        if start_idx < 0:
            failures.append(
                PatchFailure(
                    path=path,
                    hunk_index=seg_index,
                    expected_start_line=max(1, cursor + 1),
                    reason="context_mismatch",
                    actual_context_preview=_context_preview(working, cursor),
                    recommended_refresh=_recommended_refresh(cursor + 1, max(1, len(old_lines))),
                )
            )
            continue
        end_idx = start_idx + len(old_lines)
        working = working[:start_idx] + new_lines + working[end_idx:]
        cursor = start_idx + len(new_lines)

    if failures:
        return None, failures
    return "\n".join(working), []


def apply_unified_patch_transaction(
    *,
    patch: str,
    normalize_path: Callable[[str], str],
    read_file: Callable[[str], str | None],
    options: dict[str, object] | None = None,
    preconditions: dict[str, object] | None = None,
) -> dict[str, object]:
    opts = options if isinstance(options, dict) else {}
    conditions = preconditions if isinstance(preconditions, dict) else {}
    strip = int(opts.get("strip") or 1)
    atomic = bool(opts.get("atomic", True))
    allow_create = bool(opts.get("allow_create", True))
    allow_delete = bool(opts.get("allow_delete", True))

    expected_hashes_raw = conditions.get("expected_hashes")
    expected_hashes = expected_hashes_raw if isinstance(expected_hashes_raw, dict) else {}
    precondition_failures: list[PatchFailure] = []
    for raw_path, expected in expected_hashes.items():
        try:
            normalized = normalize_path(str(raw_path))
        except Exception:
            continue
        current = read_file(normalized)
        current_hash = hash_text(current or "")
        if normalize_expected_hash(str(expected)) != current_hash:
            precondition_failures.append(
                PatchFailure(
                    path=normalized,
                    hunk_index=0,
                    expected_start_line=1,
                    reason="precondition_hash_mismatch",
                    actual_context_preview=[],
                    recommended_refresh={"start_line": 1, "end_line": 200},
                )
            )
    if precondition_failures:
        return {
            "ok": False,
            "code": "PATCH_PRECONDITION_FAILED",
            "summary": f"{len(precondition_failures)} precondition(s) failed",
            "failures": [item.as_dict() for item in precondition_failures],
            "applied_files": [],
        }

    parsed_files, parse_error = parse_unified_diff(patch)
    begin_ops: list[BeginPatchOperation] = []
    if parse_error:
        begin_ops, begin_error = parse_begin_patch_format(patch)
        if begin_error:
            return {
                "ok": False,
                "code": parse_error,
                "summary": "Patch format is not supported",
                "failures": [],
                "applied_files": [],
            }
    elif not parsed_files:
        begin_ops, begin_error = parse_begin_patch_format(patch)
        if begin_error:
            return {
                "ok": False,
                "code": "PATCH_PARSE_FAILED",
                "summary": "No unified diff hunks were detected",
                "failures": [],
                "applied_files": [],
            }

    writes: Dict[str, str] = {}
    deletes: list[str] = []
    failures: list[PatchFailure] = []
    if parsed_files:
        for file_patch in parsed_files:
            old_path_raw = _strip_prefix(file_patch.old_path, strip)
            new_path_raw = _strip_prefix(file_patch.new_path, strip)
            old_path = None if _is_dev_null(old_path_raw) else normalize_path(old_path_raw)
            new_path = None if _is_dev_null(new_path_raw) else normalize_path(new_path_raw)
            target_path = new_path or old_path or "unknown"

            if old_path is None and not allow_create:
                failures.append(
                    PatchFailure(
                        path=target_path,
                        hunk_index=0,
                        expected_start_line=1,
                        reason="create_not_allowed",
                        actual_context_preview=[],
                        recommended_refresh={"start_line": 1, "end_line": 120},
                    )
                )
                continue
            if new_path is None and not allow_delete:
                failures.append(
                    PatchFailure(
                        path=target_path,
                        hunk_index=0,
                        expected_start_line=1,
                        reason="delete_not_allowed",
                        actual_context_preview=[],
                        recommended_refresh={"start_line": 1, "end_line": 120},
                    )
                )
                continue

            source_path = old_path or new_path
            source_content = read_file(source_path) if source_path else ""
            if old_path is not None and source_content is None:
                failures.append(
                    PatchFailure(
                        path=target_path,
                        hunk_index=0,
                        expected_start_line=1,
                        reason="file_missing",
                        actual_context_preview=[],
                        recommended_refresh={"start_line": 1, "end_line": 120},
                    )
                )
                continue
            source_text = source_content or ""
            applied_text, file_failures = apply_hunks_strict(
                source=source_text,
                hunks=file_patch.hunks,
                path=target_path,
            )
            if file_failures:
                failures.extend(file_failures)
                continue
            if new_path is None:
                if old_path:
                    deletes.append(old_path)
                continue
            writes[new_path] = applied_text or ""
    else:
        for op in begin_ops:
            path = normalize_path(op.path)
            if op.op == "delete":
                if not allow_delete:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=0,
                            expected_start_line=1,
                            reason="delete_not_allowed",
                            actual_context_preview=[],
                            recommended_refresh={"start_line": 1, "end_line": 120},
                        )
                    )
                    continue
                if read_file(path) is not None:
                    deletes.append(path)
                continue
            if op.op == "add":
                if not allow_create:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=0,
                            expected_start_line=1,
                            reason="create_not_allowed",
                            actual_context_preview=[],
                            recommended_refresh={"start_line": 1, "end_line": 120},
                        )
                    )
                    continue
                if read_file(path) is not None:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=0,
                            expected_start_line=1,
                            reason="target_exists",
                            actual_context_preview=[],
                            recommended_refresh={"start_line": 1, "end_line": 120},
                        )
                    )
                    continue
                bad_lines = [line for line in op.lines if line and not line.startswith("+")]
                if bad_lines:
                    failures.append(
                        PatchFailure(
                            path=path,
                            hunk_index=1,
                            expected_start_line=1,
                            reason="invalid_add_file_patch",
                            actual_context_preview=bad_lines[:3],
                            recommended_refresh={"start_line": 1, "end_line": 120},
                        )
                    )
                    continue
                content_lines = [line[1:] if line.startswith("+") else "" for line in op.lines]
                writes[path] = "\n".join(content_lines)
                continue
            source = read_file(path)
            if source is None:
                failures.append(
                    PatchFailure(
                        path=path,
                        hunk_index=0,
                        expected_start_line=1,
                        reason="file_missing",
                        actual_context_preview=[],
                        recommended_refresh={"start_line": 1, "end_line": 120},
                    )
                )
                continue
            applied_text, file_failures = _apply_begin_patch_update(source=source, path=path, lines=op.lines)
            if file_failures:
                failures.extend(file_failures)
                continue
            writes[path] = applied_text or ""

    if failures and atomic:
        return {
            "ok": False,
            "code": "PATCH_HUNK_MISMATCH",
            "summary": f"{len(failures)} hunk failure(s)",
            "failures": [item.as_dict() for item in failures],
            "applied_files": [],
        }

    return {
        "ok": len(failures) == 0,
        "code": "PATCH_PARTIAL_APPLY" if failures else "PATCH_APPLIED",
        "summary": "Patch applied" if not failures else f"Patch applied with {len(failures)} failure(s)",
        "failures": [item.as_dict() for item in failures],
        "writes": writes,
        "deletes": deletes,
        "applied_files": sorted(set(list(writes.keys()) + deletes)),
    }
