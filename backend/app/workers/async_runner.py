from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


class AsyncWorkerLoopRunner:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._run_in_dedicated_thread(coro)

        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop

            self._ready.clear()

            def _runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._ready.set()
                loop.run_forever()

            thread = threading.Thread(target=_runner, daemon=True, name="celery-async-runner")
            thread.start()
            self._thread = thread

        self._ready.wait()
        if self._loop is None:
            raise RuntimeError("Failed to initialize async worker event loop")
        return self._loop

    @staticmethod
    def _run_in_dedicated_thread(coro: Coroutine[Any, Any, Any]) -> Any:
        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:
                error["value"] = exc

        thread = threading.Thread(target=_runner, daemon=True, name="nested-async-runner")
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result.get("value")


_RUNNER = AsyncWorkerLoopRunner()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    return _RUNNER.run(coro)
