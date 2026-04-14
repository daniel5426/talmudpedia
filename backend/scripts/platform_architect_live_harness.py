from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from app.services.platform_architect_live_harness import (
    ArchitectLiveHarnessConfig,
    ArchitectLiveTask,
    PlatformArchitectLiveHarness,
    load_live_tasks,
    read_processed_task_ids,
    write_processed_task_ids,
    write_run_bundle,
    write_run_bundle_summary,
)


def _load_local_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    repo_root = Path(__file__).resolve().parents[2]
    for candidate in (repo_root / "backend" / ".env", repo_root / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _mint_local_dev_jwt() -> tuple[str, str] | None:
    _load_local_env_files()
    try:
        from sqlalchemy import select

        from app.db.postgres.engine import sessionmaker
        from app.db.postgres.models.agents import Agent
        from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
    except Exception:
        return None

    async def _query() -> tuple[str, str] | None:
        async with sessionmaker() as db:
            result = await db.execute(
                select(User.id, OrgMembership.tenant_id)
                .join(OrgMembership, OrgMembership.user_id == User.id)
                .join(
                    Agent,
                    (Agent.tenant_id == OrgMembership.tenant_id)
                    & (Agent.slug == "platform-architect"),
                )
                .where(OrgMembership.status == MembershipStatus.active)
                .order_by(Agent.created_at.desc())
                .limit(1)
            )
            row = result.first()
            if row is None:
                return None
            return str(row[0]), str(row[1])

    try:
        resolved = asyncio.run(_query())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            resolved = loop.run_until_complete(_query())
        finally:
            loop.close()
    if resolved is None:
        return None

    user_id, tenant_id = resolved
    secret_key = os.getenv("SECRET_KEY", "YOUR_SECRET_KEY_HERE_CHANGE_IN_PRODUCTION")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    token = jwt.encode(
        {
            "sub": user_id,
            "tenant_id": tenant_id,
            "scope": ["*"],
            "org_role": "owner",
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
        },
        secret_key,
        algorithm=algorithm,
    )
    return token, tenant_id


def _seed_local_dev_auth_defaults() -> None:
    if (
        ("PLATFORM_ARCHITECT_API_KEY" in os.environ or "TEST_API_KEY" in os.environ)
        and ("PLATFORM_ARCHITECT_TENANT_ID" in os.environ or "TEST_TENANT_ID" in os.environ)
    ):
        return
    minted = _mint_local_dev_jwt()
    if minted is None:
        return
    token, tenant_id = minted
    os.environ.setdefault("TEST_API_KEY", token)
    os.environ.setdefault("TEST_TENANT_ID", tenant_id)


def _load_context(raw: str | None) -> dict:
    if not raw:
        return {}
    candidate = Path(raw)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(raw)


def _prompt_command(args: argparse.Namespace) -> int:
    _seed_local_dev_auth_defaults()
    config = ArchitectLiveHarnessConfig.from_env()
    harness = PlatformArchitectLiveHarness(config)
    prompt = str(args.prompt or "").strip()
    if not prompt and args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit("prompt is required")
    task = ArchitectLiveTask(
        id=args.task_id or "adhoc-prompt",
        prompt=prompt,
        runtime_context=_load_context(args.context_json),
        timeout_s=args.timeout_s,
    )
    bundle = harness.run_task(task)
    path = write_run_bundle(bundle, output_dir=args.output_dir or config.output_dir)
    summary_path = write_run_bundle_summary(bundle, output_dir=args.output_dir or config.output_dir)
    print(json.dumps({"task_id": task.id, "run_id": bundle.run_id, "status": bundle.status, "report_path": str(path), "summary_path": str(summary_path)}, ensure_ascii=True))
    return 0


def _process_pending_tasks(
    *,
    harness: PlatformArchitectLiveHarness,
    tasks_file: Path,
    output_dir: str,
    state_file: Path,
    stop_on_failure: bool,
    max_tasks: int | None,
) -> int:
    processed = read_processed_task_ids(state_file)
    all_tasks = load_live_tasks(tasks_file)
    pending = [task for task in all_tasks if task.id not in processed]
    if max_tasks is not None:
        pending = pending[: max(0, max_tasks)]

    processed_count = 0
    for task in pending:
        bundle = harness.run_task(task)
        report_path = write_run_bundle(bundle, output_dir=output_dir)
        summary_path = write_run_bundle_summary(bundle, output_dir=output_dir)
        processed.add(task.id)
        write_processed_task_ids(state_file, processed)
        processed_count += 1
        print(
            json.dumps(
                {
                    "task_id": task.id,
                    "run_id": bundle.run_id,
                    "status": bundle.status,
                    "report_path": str(report_path),
                    "summary_path": str(summary_path),
                },
                ensure_ascii=True,
            )
        )
        if stop_on_failure and str(bundle.status or "").lower() not in {"completed", "passed"}:
            break
    return processed_count


def _queue_command(args: argparse.Namespace) -> int:
    _seed_local_dev_auth_defaults()
    config = ArchitectLiveHarnessConfig.from_env()
    harness = PlatformArchitectLiveHarness(config)
    tasks_file = Path(args.tasks_file)
    output_dir = args.output_dir or config.output_dir
    state_file = Path(args.state_file or (Path(output_dir) / "processed_tasks.json"))

    if args.watch:
        while True:
            processed_count = _process_pending_tasks(
                harness=harness,
                tasks_file=tasks_file,
                output_dir=output_dir,
                state_file=state_file,
                stop_on_failure=args.stop_on_failure,
                max_tasks=args.max_tasks,
            )
            if processed_count == 0:
                time.sleep(max(1, int(args.poll_seconds)))
                continue
            if args.stop_on_failure:
                break
        return 0

    _process_pending_tasks(
        harness=harness,
        tasks_file=tasks_file,
        output_dir=output_dir,
        state_file=state_file,
        stop_on_failure=args.stop_on_failure,
        max_tasks=args.max_tasks,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live harness for platform-architect runs against a real tenant/runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompt_parser = subparsers.add_parser("prompt", help="Run one live architect prompt and persist a full run bundle.")
    prompt_parser.add_argument("--prompt", help="Inline prompt text.")
    prompt_parser.add_argument("--prompt-file", help="Path to a text file containing the prompt.")
    prompt_parser.add_argument("--context-json", help="Inline JSON or a file path for runtime context.")
    prompt_parser.add_argument("--task-id", help="Task id used in the persisted bundle filename.")
    prompt_parser.add_argument("--timeout-s", type=int, help="Override run timeout seconds.")
    prompt_parser.add_argument("--output-dir", help="Directory for persisted run bundles.")
    prompt_parser.set_defaults(func=_prompt_command)

    queue_parser = subparsers.add_parser("queue", help="Process a JSON/JSONL task queue of live architect prompts.")
    queue_parser.add_argument("--tasks-file", required=True, help="JSON array or JSONL file of tasks.")
    queue_parser.add_argument("--output-dir", help="Directory for persisted run bundles.")
    queue_parser.add_argument("--state-file", help="JSON file tracking processed task ids.")
    queue_parser.add_argument("--watch", action="store_true", help="Poll the task file continuously for new tasks.")
    queue_parser.add_argument("--poll-seconds", type=int, default=10, help="Watch-mode poll interval.")
    queue_parser.add_argument("--stop-on-failure", action="store_true", help="Stop processing after the first non-completed run.")
    queue_parser.add_argument("--max-tasks", type=int, help="Process at most this many pending tasks per pass.")
    queue_parser.set_defaults(func=_queue_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
