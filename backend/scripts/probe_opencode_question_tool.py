#!/usr/bin/env python3
"""Probe OpenCode question-tool protocol end-to-end.

This script can launch a local OpenCode server, run a prompt that forces the
question tool, reply to the question, and print the exact event sequence and
payload shapes observed from /global/event.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class ProbeResult:
    session_id: str = ""
    question_id: str = ""
    event_counts: dict[str, int] = field(default_factory=dict)
    question_asked_payload: dict[str, Any] | None = None
    question_replied_payload: dict[str, Any] | None = None
    final_assistant_text: str = ""


class OpenCodeQuestionProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float, verbose: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verbose = verbose
        self._stop_event = threading.Event()
        self._session_id = ""
        self._events: list[dict[str, Any]] = []
        self._events_lock = threading.Lock()

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
        expect_json: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = requests.request(method=method, url=url, json=json_payload, timeout=timeout)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed ({response.status_code}): {response.text[:400]}")
        if not expect_json:
            return response.text
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type and not response.text.strip().startswith(("{", "[")):
            raise RuntimeError(f"{method} {path} returned unexpected content-type: {content_type}")
        return response.json()

    def _wait_for_server(self, max_wait_seconds: float = 20.0) -> None:
        deadline = time.time() + max_wait_seconds
        last_error = "unknown"
        while time.time() < deadline:
            try:
                payload = self._request("GET", "/session", timeout=5.0)
                if isinstance(payload, list):
                    return
                last_error = f"unexpected payload type: {type(payload).__name__}"
            except Exception as exc:  # pragma: no cover - debugging utility
                last_error = str(exc)
            time.sleep(0.4)
        raise RuntimeError(f"OpenCode server did not become ready: {last_error}")

    def _event_stream_worker(self) -> None:
        headers = {"Accept": "text/event-stream"}
        url = f"{self.base_url}/global/event"
        with requests.get(url, headers=headers, stream=True, timeout=(10, None)) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"GET /global/event failed ({response.status_code}): {response.text[:300]}")
            for raw_line in response.iter_lines(decode_unicode=True):
                if self._stop_event.is_set():
                    return
                line = (raw_line or "").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line:
                    continue
                try:
                    wrapper = json.loads(line)
                except Exception:
                    continue
                payload = wrapper.get("payload") if isinstance(wrapper, dict) else None
                if not isinstance(payload, dict):
                    continue
                with self._events_lock:
                    self._events.append(payload)

    @staticmethod
    def _extract_session_id(properties: dict[str, Any]) -> str:
        direct = str(properties.get("sessionID") or properties.get("sessionId") or "").strip()
        if direct:
            return direct
        info = properties.get("info")
        if isinstance(info, dict):
            nested = str(info.get("sessionID") or info.get("sessionId") or "").strip()
            if nested:
                return nested
        return ""

    def _matching_events(self) -> list[dict[str, Any]]:
        with self._events_lock:
            source = list(self._events)
        if not self._session_id:
            return source
        matched: list[dict[str, Any]] = []
        for payload in source:
            properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
            if not properties:
                continue
            session_id = self._extract_session_id(properties)
            if session_id == self._session_id:
                matched.append(payload)
        return matched

    def _wait_for_question(self, *, poll_interval: float = 0.4) -> dict[str, Any]:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            payload = self._request("GET", "/question", timeout=10.0)
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    session_id = str(item.get("sessionID") or item.get("sessionId") or "").strip()
                    if session_id == self._session_id:
                        return item
            time.sleep(poll_interval)
        raise RuntimeError("Timed out waiting for /question entry for this session")

    def _wait_for_idle_event(self, *, poll_interval: float = 0.3) -> None:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            for event in self._matching_events():
                if str(event.get("type") or "") == "session.idle":
                    return
            time.sleep(poll_interval)
        raise RuntimeError("Timed out waiting for session.idle")

    def _read_final_assistant_text(self) -> str:
        payload = self._request("GET", f"/session/{self._session_id}/message", timeout=30.0)
        if not isinstance(payload, list):
            return ""
        latest_assistant_text = ""
        for message in payload:
            if not isinstance(message, dict):
                continue
            info = message.get("info") if isinstance(message.get("info"), dict) else {}
            if str(info.get("role") or "").strip().lower() != "assistant":
                continue
            parts = message.get("parts") if isinstance(message.get("parts"), list) else []
            text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if str(part.get("type") or "").strip().lower() != "text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
            if text_parts:
                latest_assistant_text = "\n".join(text_parts)
        return latest_assistant_text

    def run(self, *, answer: str) -> ProbeResult:
        result = ProbeResult()
        self._wait_for_server()
        self._log("OpenCode server is ready.")

        session_payload = {
            "title": f"question-probe-{uuid.uuid4().hex[:8]}",
            "permission": [{"permission": "question", "pattern": "*", "action": "allow"}],
        }
        session = self._request("POST", "/session", json_payload=session_payload, timeout=30.0)
        if not isinstance(session, dict):
            raise RuntimeError("POST /session returned an unexpected payload")
        self._session_id = str(session.get("id") or "").strip()
        if not self._session_id:
            raise RuntimeError("POST /session response is missing id")
        result.session_id = self._session_id
        self._log(f"Created session: {self._session_id}")

        stream_thread = threading.Thread(target=self._event_stream_worker, name="opencode-global-event-stream", daemon=True)
        stream_thread.start()
        time.sleep(0.2)

        prompt = (
            'Use the question tool first. Ask one question with header "Need decision", '
            'question "Pick mode", options A and B. '
            'After I answer, print exactly: "received:<answer>" and finish.'
        )
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        prompt_payload = {
            "messageID": message_id,
            "parts": [{"type": "text", "text": prompt}],
        }
        self._request(
            "POST",
            f"/session/{self._session_id}/prompt_async",
            json_payload=prompt_payload,
            timeout=30.0,
            expect_json=False,
        )
        self._log("Submitted prompt_async.")

        question = self._wait_for_question()
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            raise RuntimeError("Question payload missing id")
        result.question_id = question_id
        self._log(f"Captured question id: {question_id}")

        reply_payload = {"answers": [[answer]]}
        self._request("POST", f"/question/{question_id}/reply", json_payload=reply_payload, timeout=30.0, expect_json=False)
        self._log(f"Posted question reply: {reply_payload}")

        self._wait_for_idle_event()
        self._log("Observed session.idle.")

        matching_events = self._matching_events()
        for event in matching_events:
            event_type = str(event.get("type") or "")
            result.event_counts[event_type] = result.event_counts.get(event_type, 0) + 1
            if event_type == "question.asked" and result.question_asked_payload is None:
                result.question_asked_payload = event
            if event_type == "question.replied" and result.question_replied_payload is None:
                result.question_replied_payload = event

        result.final_assistant_text = self._read_final_assistant_text()

        self._stop_event.set()
        stream_thread.join(timeout=1.0)
        return result


def launch_local_opencode_server(*, port: int, cwd: str) -> subprocess.Popen[str]:
    command = ["npx", "-y", "opencode-ai", "serve", "--hostname", "127.0.0.1", "--port", str(port)]
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )
    return process


def stream_process_output(process: subprocess.Popen[str], *, stop_event: threading.Event) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        if stop_event.is_set():
            return
        print(f"[opencode] {line.rstrip()}", flush=True)


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    process.terminate()
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    process.kill()
    process.wait(timeout=5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe OpenCode question tool event protocol.")
    parser.add_argument(
        "--base-url",
        default="",
        help="Existing OpenCode server base URL. If set, the script will not launch a server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4101,
        help="Port to use when launching local OpenCode server.",
    )
    parser.add_argument(
        "--server-cwd",
        default=os.getcwd(),
        help="Working directory used when launching local OpenCode server.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for waiting on question/idle protocol steps.",
    )
    parser.add_argument(
        "--answer",
        default="A",
        help="Answer label to send back to question tool.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce progress logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.strip() or f"http://127.0.0.1:{args.port}"
    verbose = not args.quiet

    server_process: subprocess.Popen[str] | None = None
    output_stop = threading.Event()
    output_thread: threading.Thread | None = None

    try:
        if not args.base_url.strip():
            print(f"Launching OpenCode server on {base_url} ...", flush=True)
            server_process = launch_local_opencode_server(port=args.port, cwd=args.server_cwd)
            output_thread = threading.Thread(
                target=stream_process_output,
                args=(server_process,),
                kwargs={"stop_event": output_stop},
                daemon=True,
            )
            output_thread.start()

        probe = OpenCodeQuestionProbe(base_url=base_url, timeout_seconds=float(args.timeout_seconds), verbose=verbose)
        result = probe.run(answer=str(args.answer))

        print("\n=== Probe Summary ===", flush=True)
        print(f"session_id: {result.session_id}", flush=True)
        print(f"question_id: {result.question_id}", flush=True)
        print(f"event_counts: {json.dumps(result.event_counts, sort_keys=True)}", flush=True)
        print("question.asked payload:", flush=True)
        print(json.dumps(result.question_asked_payload, ensure_ascii=True, sort_keys=True, indent=2), flush=True)
        print("question.replied payload:", flush=True)
        print(json.dumps(result.question_replied_payload, ensure_ascii=True, sort_keys=True, indent=2), flush=True)
        print("final assistant text preview:", flush=True)
        print((result.final_assistant_text or "")[:500], flush=True)
        return 0
    except Exception as exc:
        print(f"Probe failed: {exc}", flush=True)
        return 1
    finally:
        output_stop.set()
        if output_thread is not None:
            output_thread.join(timeout=0.8)
        if server_process is not None:
            stop_process(server_process)


if __name__ == "__main__":
    raise SystemExit(main())
