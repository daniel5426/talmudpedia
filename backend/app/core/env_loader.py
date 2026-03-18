from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE_VAR = "TALMUDPEDIA_ENV_FILE"
ENV_PROFILE_VAR = "TALMUDPEDIA_ENV_PROFILE"


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def running_under_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def resolve_backend_env_file(
    *,
    backend_dir: Path | None = None,
    prefer_test_env: bool = False,
) -> Path:
    root = (backend_dir or backend_root()).resolve()

    explicit = (os.getenv(ENV_FILE_VAR) or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Configured env file does not exist: {path}")
        return path

    profile = (os.getenv(ENV_PROFILE_VAR) or "").strip().lower()
    use_test_profile = prefer_test_env or profile == "test" or (not profile and running_under_pytest())

    candidates: list[Path] = []
    if use_test_profile:
        candidates.extend(
            [
                root / ".env.test",
                root / ".env.test.example",
            ]
        )
    candidates.append(root / ".env")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def load_backend_env(
    *,
    backend_dir: Path | None = None,
    override: bool,
    prefer_test_env: bool = False,
    required: bool = False,
) -> Path | None:
    path = resolve_backend_env_file(
        backend_dir=backend_dir,
        prefer_test_env=prefer_test_env,
    )
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Unable to locate backend env file: {path}")
        return None

    load_dotenv(path, override=override)
    os.environ.setdefault(ENV_FILE_VAR, str(path))
    if prefer_test_env or running_under_pytest():
        os.environ.setdefault(ENV_PROFILE_VAR, "test")
    return path
