from __future__ import annotations

import logging
import os
import pickle
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


class DurableMemorySaver(MemorySaver):
    """Persist LangGraph checkpoints to disk for cross-process durability."""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or os.getenv("AGENT_CHECKPOINTER_PATH", "/tmp/talmudpedia_langgraph_checkpoints.pkl"))
        self._io_lock = threading.RLock()
        super().__init__()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        with self._io_lock:
            if not self._path.exists():
                return
            try:
                with self._path.open("rb") as fh:
                    payload = pickle.load(fh)
            except Exception as exc:
                logger.warning("Failed to load durable checkpointer state", extra={"error": str(exc), "path": str(self._path)})
                return

            storage_raw = payload.get("storage") if isinstance(payload, dict) else None
            writes_raw = payload.get("writes") if isinstance(payload, dict) else None
            blobs_raw = payload.get("blobs") if isinstance(payload, dict) else None

            storage = defaultdict(lambda: defaultdict(dict))
            if isinstance(storage_raw, dict):
                for thread_id, ns_map in storage_raw.items():
                    ns_default = defaultdict(dict)
                    if isinstance(ns_map, dict):
                        for checkpoint_ns, checkpoints in ns_map.items():
                            if isinstance(checkpoints, dict):
                                ns_default[str(checkpoint_ns)] = dict(checkpoints)
                    storage[str(thread_id)] = ns_default

            writes = defaultdict(dict)
            if isinstance(writes_raw, dict):
                for key, value in writes_raw.items():
                    if isinstance(key, tuple) and isinstance(value, dict):
                        writes[key] = dict(value)

            blobs: dict[Any, Any] = {}
            if isinstance(blobs_raw, dict):
                blobs = dict(blobs_raw)

            self.storage = storage
            self.writes = writes
            self.blobs = blobs

    def _persist_to_disk(self) -> None:
        with self._io_lock:
            parent = self._path.parent
            parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "storage": {
                    thread_id: {
                        checkpoint_ns: dict(checkpoints)
                        for checkpoint_ns, checkpoints in ns_map.items()
                    }
                    for thread_id, ns_map in self.storage.items()
                },
                "writes": {
                    key: dict(value)
                    for key, value in self.writes.items()
                },
                "blobs": dict(self.blobs),
            }
            temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            with temp_path.open("wb") as fh:
                pickle.dump(payload, fh)
            temp_path.replace(self._path)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        with self._io_lock:
            result = super().put(config, checkpoint, metadata, new_versions)
            self._persist_to_disk()
            return result

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with self._io_lock:
            super().put_writes(config, writes, task_id, task_path)
            self._persist_to_disk()

    def delete_thread(self, thread_id: str) -> None:
        with self._io_lock:
            super().delete_thread(thread_id)
            self._persist_to_disk()
