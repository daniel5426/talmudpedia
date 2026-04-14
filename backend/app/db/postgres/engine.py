import os
import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine, async_sessionmaker, AsyncEngine

def _build_local_database_url() -> str:
    """
    Build a local DB URL without inheriting remote POSTGRES_* values.
    Override with LOCAL_POSTGRES_* only when needed.
    """
    user = os.getenv("LOCAL_POSTGRES_USER", "postgres")
    password = os.getenv("LOCAL_POSTGRES_PASSWORD", "postgres")
    host = os.getenv("LOCAL_POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("LOCAL_POSTGRES_PORT", "5432")
    db = os.getenv("LOCAL_POSTGRES_DB", "talmudpedia_dev")
    quoted_password = urllib.parse.quote_plus(password)
    return f"postgresql+asyncpg://{user}:{quoted_password}@{host}:{port}/{db}"


def _build_legacy_postgres_url() -> str:
    """
    Keep pre-existing fallback behavior for environments not using DB_TARGET.
    """
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "postgres")
    quoted_password = urllib.parse.quote_plus(password)
    return f"postgresql+asyncpg://{user}:{quoted_password}@{host}:{port}/{db}"


def _resolve_database_url() -> tuple[str, str]:
    """
    Resolve DB URL with explicit target switching.

    DB_TARGET values:
    - local: use DATABASE_URL_LOCAL if provided, else LOCAL_POSTGRES_* defaults
    - remote/supabase/prod: use DATABASE_URL_REMOTE, fallback DATABASE_URL
    - unset/other: default to local
    """
    target = (os.getenv("DB_TARGET") or "").strip().lower()

    if target == "local":
        local_url = (os.getenv("DATABASE_URL_LOCAL") or "").strip()
        return (local_url or _build_local_database_url(), "local")

    if target in {"remote", "supabase", "prod", "production"}:
        remote_url = (os.getenv("DATABASE_URL_REMOTE") or os.getenv("DATABASE_URL") or "").strip()
        if remote_url:
            return (remote_url, "remote")
        raise RuntimeError("DB_TARGET is set to remote, but DATABASE_URL_REMOTE or DATABASE_URL is not configured.")

    local_url = (os.getenv("DATABASE_URL_LOCAL") or "").strip()
    return (local_url or _build_local_database_url(), "local-default")


def _normalize_database_url(raw_url: str) -> str:
    database_url = raw_url
    try:
        if "://" in database_url:
            scheme, rest = database_url.split("://", 1)
            if scheme in {"postgres", "postgresql"} and "+asyncpg" not in scheme:
                scheme = "postgresql+asyncpg"

            if "@" in rest:
                creds, location = rest.rsplit("@", 1)
                if ":" in creds:
                    user, password = creds.split(":", 1)
                    print(f"DEBUG: Parsed DB User: '{user}'")
                    print(f"DEBUG: Parsed DB Host: '{location}'")
                    encoded_password = urllib.parse.quote_plus(password)
                    database_url = f"{scheme}://{user}:{encoded_password}@{location}"
                else:
                    database_url = f"{scheme}://{rest}"
            else:
                database_url = f"{scheme}://{rest}"
    except Exception as exc:
        print(f"ERROR: Failed to normalize DATABASE_URL password: {exc}")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


DATABASE_URL, DATABASE_TARGET = _resolve_database_url()
DATABASE_URL = _normalize_database_url(DATABASE_URL)
print(
    "DEBUG: Initializing DB Engine target="
    f"{DATABASE_TARGET} host={DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'HIDDEN'}"
)


def create_async_engine() -> AsyncEngine:
    """
    Creates and returns a new SQLAlchemy AsyncEngine instance.
    """
    # asyncpg struggles with disabling prepared statements reliably in some SQLAlchemy configurations
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    if "postgresql+psycopg://" not in url and "socket" not in url:
        # Fallback if URL was "postgres://" or otherwise
        if "postgres://" in url:
            url = url.replace("postgres://", "postgresql+psycopg://")
        elif "postgresql://" in url:
            url = url.replace("postgresql://", "postgresql+psycopg://")

    print(f"DEBUG: Creating Async Engine with Psycopg (v3) and prepare_threshold=None")
    return _create_async_engine(
        url,
        echo=False,
        # Enable pre-ping to ensure connections in the pool are alive
        pool_pre_ping=True,
        # Standard QueuePool (default) is better for performance than NullPool
        # especially when SSL handshakes are expensive (5s latency observed).
        # We manually disable prepared statements below for PgBouncer compatibility.
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
        # Disable prepared statements for PgBouncer compatibility (Psycopg v3 specific)
        connect_args={"prepare_threshold": None},
    )

# Create a global engine instance
engine = create_async_engine()

# Create a session factory
# This is used in app/db/postgres/session.py as:
# async with sessionmaker() as session:
sessionmaker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)
