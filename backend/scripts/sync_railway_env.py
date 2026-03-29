#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync dedicated deployment env files into Railway services."
    )
    parser.add_argument(
        "--backend-file",
        default="backend/.env.railway",
        help="Env file to sync into the backend service.",
    )
    parser.add_argument(
        "--frontend-file",
        default="frontend-reshet/.env.railway",
        help="Env file to sync into the frontend service.",
    )
    parser.add_argument(
        "--backend-service",
        default="backend",
        help="Railway backend service name.",
    )
    parser.add_argument(
        "--worker-service",
        default="backend-worker",
        help="Railway worker service name.",
    )
    parser.add_argument(
        "--frontend-service",
        default="frontend",
        help="Railway frontend service name.",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Do not sync the backend env file.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Do not sync the frontend env file.",
    )
    parser.add_argument(
        "--sync-worker",
        action="store_true",
        help="Also sync the backend env file into the backend-worker service.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned updates without sending them to Railway.",
    )
    return parser.parse_args()


def require_railway_cli() -> None:
    if shutil.which("railway"):
        return
    raise SystemExit("Railway CLI is not installed or not on PATH.")


def load_env_file(path_str: str) -> tuple[Path, dict[str, str]]:
    path = Path(path_str).resolve()
    if not path.exists():
        raise SystemExit(f"Env file does not exist: {path}")
    values = dotenv_values(path)
    result: dict[str, str] = {}
    for key, value in values.items():
        if key is None or value is None:
            continue
        result[key] = str(value)
    return path, result


def set_service_vars(service: str, values: dict[str, str], *, dry_run: bool) -> None:
    if not values:
        print(f"[skip] {service}: no variables found")
        return
    print(f"[sync] {service}: {len(values)} variables")
    if dry_run:
        for key in sorted(values):
            print(f"  - {key}")
        return
    for key, value in values.items():
        _set_service_var_with_retry(service=service, key=key, value=value)


def _set_service_var_with_retry(*, service: str, key: str, value: str, max_attempts: int = 6) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            subprocess.run(
                ["railway", "variable", "set", f"{key}={value}", "--service", service],
                check=True,
                text=True,
                capture_output=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            stderr = getattr(exc, "stderr", None) or ""
            stdout = getattr(exc, "stdout", None) or ""
            combined = f"{stdout}\n{stderr}".lower()
            if "rate limit" not in combined or attempt >= max_attempts:
                raise
            delay_seconds = min(30, 2 ** (attempt - 1))
            print(
                f"[retry] {service}: Railway rate limited variable `{key}` "
                f"(attempt {attempt}/{max_attempts}), sleeping {delay_seconds}s"
            )
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error


def main() -> int:
    args = parse_args()
    require_railway_cli()

    if not args.skip_backend:
        backend_path, backend_values = load_env_file(args.backend_file)
        print(f"[file] backend: {backend_path}")
        set_service_vars(args.backend_service, backend_values, dry_run=args.dry_run)
        if args.sync_worker:
            set_service_vars(args.worker_service, backend_values, dry_run=args.dry_run)

    if not args.skip_frontend:
        frontend_path, frontend_values = load_env_file(args.frontend_file)
        print(f"[file] frontend: {frontend_path}")
        set_service_vars(args.frontend_service, frontend_values, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Railway sync failed: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode)
