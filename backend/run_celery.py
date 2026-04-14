#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.env_loader import load_backend_env, running_under_pytest

load_backend_env(backend_dir=Path(__file__).parent, override=not running_under_pytest())

from app.workers.celery_app import celery_app
from app.workers.dev_reload import DEFAULT_POLL_SECONDS, run_celery_with_reload


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--watch", action="append", dest="watch_paths", default=[])
    parser.add_argument("celery_args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    celery_args = list(parsed.celery_args or [])
    if celery_args[:1] == ["--"]:
        celery_args = celery_args[1:]
    if not celery_args:
        celery_args = ["worker"]
    return parsed, celery_args

if __name__ == "__main__":
    options, celery_args = _parse_args(sys.argv[1:])
    if options.reload:
        raise SystemExit(
            run_celery_with_reload(
                script_path=Path(__file__).resolve(),
                celery_args=celery_args,
                watch_paths=options.watch_paths or None,
                poll_seconds=options.poll_seconds,
            )
        )
    celery_app.start(argv=celery_args)
