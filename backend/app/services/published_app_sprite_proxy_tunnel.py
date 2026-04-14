from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Dict, Tuple
from urllib.parse import urlparse

import websockets


class SpriteProxyTunnelError(Exception):
    pass


logger = logging.getLogger(__name__)
_TUNNEL_WS_CONNECT_DELAYS_SECONDS = (0.0, 0.2, 0.6)


@dataclass
class _TunnelState:
    server: asyncio.base_events.Server
    local_host: str
    local_port: int


class SpriteProxyTunnelManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tunnels: Dict[Tuple[str, str, int], _TunnelState] = {}

    @staticmethod
    def _proxy_ws_url(*, api_base_url: str, sprite_name: str) -> str:
        parsed = urlparse(str(api_base_url or "https://api.sprites.dev").rstrip("/"))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = parsed.path.rstrip("/")
        return f"{scheme}://{parsed.netloc}{path}/v1/sprites/{sprite_name}/proxy"

    async def ensure_tunnel(
        self,
        *,
        api_base_url: str,
        api_token: str,
        sprite_name: str,
        remote_host: str,
        remote_port: int,
    ) -> str:
        key = (str(sprite_name), str(remote_host), int(remote_port))
        async with self._lock:
            existing = self._tunnels.get(key)
            if existing is not None and existing.server.is_serving():
                return f"http://{existing.local_host}:{existing.local_port}"

            async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                ws = None
                relay_tasks: list[asyncio.Task] = []
                try:
                    last_exc: Exception | None = None
                    for delay in _TUNNEL_WS_CONNECT_DELAYS_SECONDS:
                        if delay > 0:
                            await asyncio.sleep(delay)
                        try:
                            ws = await websockets.connect(
                                self._proxy_ws_url(api_base_url=api_base_url, sprite_name=sprite_name),
                                additional_headers={"Authorization": f"Bearer {api_token}"},
                                open_timeout=15.0,
                                close_timeout=5.0,
                                ping_interval=20.0,
                                ping_timeout=20.0,
                                max_size=None,
                            )
                            break
                        except Exception as exc:
                            last_exc = exc
                    if ws is None:
                        raise SpriteProxyTunnelError(
                            f"Failed to connect Sprite proxy tunnel for {sprite_name}:{remote_port}: {last_exc}"
                        ) from last_exc
                    await ws.send(json.dumps({"host": remote_host, "port": int(remote_port)}))
                    initial_message = await ws.recv()
                    if isinstance(initial_message, str):
                        try:
                            initial_payload = json.loads(initial_message)
                        except Exception as exc:
                            raise SpriteProxyTunnelError(
                                f"Sprite proxy returned invalid initial handshake payload: {initial_message[:200]}"
                            ) from exc
                        if str(initial_payload.get("status") or "").strip().lower() != "connected":
                            raise SpriteProxyTunnelError(
                                f"Sprite proxy failed to connect tunnel target: {initial_payload}"
                            )
                    elif initial_message:
                        raise SpriteProxyTunnelError("Sprite proxy returned unexpected binary handshake payload.")

                    async def _tcp_to_ws() -> None:
                        while True:
                            chunk = await reader.read(65536)
                            if not chunk:
                                try:
                                    await ws.close()
                                except Exception:
                                    pass
                                break
                            await ws.send(chunk)

                    async def _ws_to_tcp() -> None:
                        async for message in ws:
                            if isinstance(message, str):
                                writer.write(message.encode("utf-8"))
                            else:
                                writer.write(message)
                            await writer.drain()

                    relay_tasks = [
                        asyncio.create_task(_tcp_to_ws()),
                        asyncio.create_task(_ws_to_tcp()),
                    ]
                    done, pending = await asyncio.wait(relay_tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()
                    for task in done:
                        exc = task.exception()
                        if exc is not None:
                            raise exc
                except Exception as exc:
                    logger.debug(
                        "Sprite proxy tunnel connection failed sprite=%s host=%s port=%s error=%s",
                        sprite_name,
                        remote_host,
                        remote_port,
                        exc,
                    )
                finally:
                    for task in relay_tasks:
                        if not task.done():
                            task.cancel()
                    if ws is not None:
                        try:
                            await ws.close()
                        except Exception:
                            pass
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

            server = await asyncio.start_server(_handle_client, host="127.0.0.1", port=0)
            socket = next(iter(server.sockets or []), None)
            if socket is None:
                server.close()
                await server.wait_closed()
                raise SpriteProxyTunnelError("Sprite proxy tunnel did not allocate a local socket.")
            local_host, local_port = socket.getsockname()[:2]
            state = _TunnelState(server=server, local_host=str(local_host), local_port=int(local_port))
            self._tunnels[key] = state
            return f"http://{state.local_host}:{state.local_port}"


_SPRITE_PROXY_TUNNEL_MANAGER = SpriteProxyTunnelManager()


def get_sprite_proxy_tunnel_manager() -> SpriteProxyTunnelManager:
    return _SPRITE_PROXY_TUNNEL_MANAGER
