from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

from app.agent.components.llm.langchain_provider import LangChainProviderAdapter
from app.agent.core.llm_adapter import extract_usage_payload_from_message
from app.db.postgres.models.registry import ModelProviderType


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=True)
    except Exception:
        return repr(value)


async def _run_once(*, model: str, prompt: str, max_tokens: int | None, temperature: float | None) -> None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY in environment")

    provider = LangChainProviderAdapter(
        provider=ModelProviderType.GOOGLE,
        model=model,
        api_key=api_key,
    )

    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = await provider.generate(
        messages=[HumanMessage(content=prompt)],
        **kwargs,
    )

    extracted_usage = extract_usage_payload_from_message(response)
    response_metadata = getattr(response, "response_metadata", None)
    direct_usage_metadata = getattr(response, "usage_metadata", None)
    usage_metadata = None
    if isinstance(response_metadata, dict):
        usage_metadata = (
            response_metadata.get("usage_metadata")
            or response_metadata.get("usageMetadata")
            or response_metadata.get("usage")
            or response_metadata.get("token_usage")
            or response_metadata.get("tokenUsage")
        )

    print("MODEL")
    print(model)
    print()
    print("MESSAGE_TYPE")
    print(type(response).__name__)
    print()
    print("TEXT")
    print(getattr(response, "content", ""))
    print()
    print("RESPONSE_METADATA")
    print(_safe_json(response_metadata))
    print()
    print("DIRECT_USAGE_METADATA_ATTR")
    print(_safe_json(direct_usage_metadata))
    print()
    print("NESTED_USAGE_METADATA")
    print(_safe_json(usage_metadata))
    print()
    print("EXTRACTED_USAGE")
    print(_safe_json(extracted_usage))
    print()
    print("ADDITIONAL_KWARGS")
    print(_safe_json(getattr(response, "additional_kwargs", None)))


async def _run_stream(*, model: str, prompt: str, max_tokens: int | None, temperature: float | None) -> None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY in environment")

    provider = LangChainProviderAdapter(
        provider=ModelProviderType.GOOGLE,
        model=model,
        api_key=api_key,
    )

    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature

    last_chunk: Any = None
    chunk_count = 0
    async for chunk in provider.stream(
        messages=[HumanMessage(content=prompt)],
        **kwargs,
    ):
        chunk_count += 1
        last_chunk = chunk

    extracted_usage = extract_usage_payload_from_message(last_chunk)
    print("STREAM_CHUNK_COUNT")
    print(chunk_count)
    print()
    print("LAST_CHUNK_TYPE")
    print(type(last_chunk).__name__ if last_chunk is not None else None)
    print()
    print("LAST_CHUNK_RESPONSE_METADATA")
    print(_safe_json(getattr(last_chunk, "response_metadata", None)))
    print()
    print("LAST_CHUNK_DIRECT_USAGE_METADATA_ATTR")
    print(_safe_json(getattr(last_chunk, "usage_metadata", None)))
    print()
    print("LAST_CHUNK_EXTRACTED_USAGE")
    print(_safe_json(extracted_usage))


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug real LangChain Gemini usage metadata")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Provider model id")
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: ok",
        help="Tiny prompt to minimize spend",
    )
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--stream", action="store_true", help="Run the provider stream path instead of ainvoke")
    args = parser.parse_args()

    if args.stream:
        asyncio.run(
            _run_stream(
                model=args.model,
                prompt=args.prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        )
        return

    asyncio.run(
        _run_once(
            model=args.model,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    )


if __name__ == "__main__":
    main()
