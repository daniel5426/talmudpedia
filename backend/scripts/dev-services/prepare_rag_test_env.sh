#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
TEST_ENV_FILE="$BACKEND_DIR/.env.test"

if [[ ! -f "$TEST_ENV_FILE" ]]; then
  echo "Missing test env file: $TEST_ENV_FILE" >&2
  exit 1
fi

export TALMUDPEDIA_ENV_FILE="$TEST_ENV_FILE"
export TALMUDPEDIA_ENV_PROFILE="${TALMUDPEDIA_ENV_PROFILE:-test}"
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$BACKEND_DIR"

ensure_docker_container() {
  local name="$1"
  if ! docker inspect "$name" >/dev/null 2>&1; then
    return 1
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$name")" != "true" ]]; then
    docker start "$name" >/dev/null
  fi
}

if command -v docker >/dev/null 2>&1; then
  ensure_docker_container "${LOCAL_PGVECTOR_CONTAINER_NAME:-talmudpedia-pgvector-dev}" || true
  ensure_docker_container "${LOCAL_CRAWL4AI_CONTAINER_NAME:-talmudpedia-crawl4ai-dev}" || true
fi

python3 - <<'PY'
import asyncio
import os
import socket
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

from app.core.env_loader import load_backend_env

load_backend_env(override=False, prefer_test_env=False)
load_dotenv(".env.test", override=True)
os.environ["TALMUDPEDIA_ENV_FILE"] = os.path.abspath(".env.test")
os.environ["TALMUDPEDIA_ENV_PROFILE"] = "test"

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus


def require_socket(name: str, host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            print(f"[ok] {name}: {host}:{port}")
    except OSError as exc:
        print(f"[missing] {name}: {host}:{port} ({exc})")
        raise SystemExit(1) from exc


async def require_http(name: str, url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        print(f"[ok] {name}: {url}")
    except Exception as exc:
        print(f"[missing] {name}: {url} ({exc})")
        raise SystemExit(1) from exc


async def require_tenant_models() -> None:
    email = (os.getenv("TEST_TENANT_EMAIL") or "").strip()
    chat_model_id = (os.getenv("TEST_CHAT_MODEL_SLUG") or "").strip()
    embed_model_id = (os.getenv("TEST_EMBED_MODEL_SLUG") or "").strip()
    if not email:
        print("[missing] TEST_TENANT_EMAIL")
        raise SystemExit(1)
    async with sessionmaker() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            print(f"[missing] tenant user: {email}")
            raise SystemExit(1)
        membership = await session.scalar(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.status == MembershipStatus.active,
            )
        )
        if not membership:
            print(f"[missing] active membership: {email}")
            raise SystemExit(1)
        tenant_id = membership.tenant_id
        print(f"[ok] tenant: {tenant_id}")

        if chat_model_id:
            chat_model = await session.get(ModelRegistry, chat_model_id)
            if not chat_model or chat_model.capability_type != ModelCapabilityType.CHAT or chat_model.status != ModelStatus.ACTIVE:
                print(f"[missing] active chat model: {chat_model_id}")
                raise SystemExit(1)
            print(f"[ok] chat model: {chat_model_id}")

        if embed_model_id:
            embed_model = await session.get(ModelRegistry, embed_model_id)
            if not embed_model or embed_model.capability_type != ModelCapabilityType.EMBEDDING or embed_model.status != ModelStatus.ACTIVE:
                print(f"[missing] active embedding model: {embed_model_id}")
                raise SystemExit(1)
            print(f"[ok] embedding model: {embed_model_id}")


async def main() -> None:
    db_url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    pgvector_url = os.getenv("PGVECTOR_CONNECTION_STRING")
    crawl4ai_base = (os.getenv("CRAWL4AI_BASE_URL") or "").rstrip("/")
    if not db_url or not pgvector_url or not crawl4ai_base:
        print("[missing] one of DATABASE_URL_LOCAL/DATABASE_URL, PGVECTOR_CONNECTION_STRING, CRAWL4AI_BASE_URL")
        raise SystemExit(1)

    db = urlparse(db_url)
    require_socket("postgres", db.hostname or "127.0.0.1", db.port or 5432)

    pg = urlparse(pgvector_url)
    require_socket("pgvector", pg.hostname or "127.0.0.1", pg.port or 5432)

    await require_http("crawl4ai", f"{crawl4ai_base}/health")
    await require_tenant_models()

    if os.getenv("OPENAI_API_KEY"):
        print("[ok] OPENAI_API_KEY present")
    else:
        print("[warn] OPENAI_API_KEY missing")
    if os.getenv("PINECONE_API_KEY"):
        print("[ok] PINECONE_API_KEY present")
    else:
        print("[warn] PINECONE_API_KEY missing")


asyncio.run(main())
PY
