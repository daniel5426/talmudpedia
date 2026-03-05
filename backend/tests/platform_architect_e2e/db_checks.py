from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text


@dataclass
class DBCheckResult:
    ok: bool
    detail: str


def _maybe_load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'").strip('"')


def _pg_from_database_url() -> dict[str, str] | None:
    url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg2", "postgresql+asyncpg"}:
        return None
    if not parsed.hostname or not parsed.username or not parsed.path:
        return None

    dbname = parsed.path.lstrip("/")
    if not dbname:
        return None

    return {
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username,
        "PGPASSWORD": parsed.password or "",
        "PGDATABASE": dbname,
    }


def _sync_database_url() -> str | None:
    url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    if not url:
        return None

    normalized = str(url).strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://") :]
    if normalized.startswith("postgresql+asyncpg://"):
        normalized = "postgresql+psycopg2://" + normalized[len("postgresql+asyncpg://") :]
    return normalized


def _sqlalchemy_scalar(sql: str) -> str | None:
    _maybe_load_backend_env()
    url = _sync_database_url()
    if not url:
        return None

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            value = conn.execute(text(sql)).scalar()
        engine.dispose()
        if value is None:
            return None
        return str(value).strip() or None
    except Exception:
        return None


def _pg_env() -> dict[str, str] | None:
    _maybe_load_backend_env()

    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    dbname = os.getenv("POSTGRES_DB")
    if all([host, port, user, dbname]):
        return {
            "PGHOST": host,
            "PGPORT": str(port),
            "PGUSER": user,
            "PGPASSWORD": password or "",
            "PGDATABASE": dbname,
        }

    return _pg_from_database_url()


def _psql_scalar(sql: str) -> str | None:
    sqlalchemy_value = _sqlalchemy_scalar(sql)
    if sqlalchemy_value is not None:
        return sqlalchemy_value

    env_bits = _pg_env()
    if env_bits is None:
        return None

    env = os.environ.copy()
    env.update(env_bits)
    proc = subprocess.run(
        ["psql", "-At", "-c", sql],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def resolve_tenant_slug(tenant_id: str) -> str | None:
    safe_tenant = str(tenant_id).replace("'", "''")
    sql = f"SELECT slug FROM tenants WHERE id = '{safe_tenant}'::uuid LIMIT 1;"
    return _psql_scalar(sql)


def check_agent_run_exists(run_id: str, tenant_id: str) -> DBCheckResult:
    safe_run = str(run_id).replace("'", "''")
    safe_tenant = str(tenant_id).replace("'", "''")
    sql = (
        "SELECT COUNT(*) FROM agent_runs "
        f"WHERE id = '{safe_run}'::uuid AND tenant_id = '{safe_tenant}'::uuid;"
    )
    output = _psql_scalar(sql)
    if output is None:
        return DBCheckResult(ok=False, detail="DB query unavailable (psql env missing or query failed)")
    ok = output == "1"
    return DBCheckResult(ok=ok, detail=f"agent_runs count={output}")
