from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

import pytest
import websockets

from app.services.published_app_sprite_proxy_tunnel import SpriteProxyTunnelManager


@pytest.mark.asyncio
async def test_sprite_proxy_tunnel_relays_bytes_and_reuses_listener():
    seen_paths: list[str] = []
    seen_auth_headers: list[str] = []
    received_payloads: list[bytes] = []

    async def handler(connection: websockets.ServerConnection) -> None:
        seen_paths.append(connection.request.path)
        seen_auth_headers.append(connection.request.headers.get("Authorization", ""))

        handshake_raw = await connection.recv()
        assert isinstance(handshake_raw, str)
        handshake = json.loads(handshake_raw)
        assert handshake == {"host": "127.0.0.1", "port": 4141}

        await connection.send(json.dumps({"status": "connected"}))

        async for message in connection:
            assert isinstance(message, bytes)
            received_payloads.append(message)
            await connection.send(b"reply:" + message)

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        ws_socket = next(iter(server.sockets or []), None)
        assert ws_socket is not None
        ws_host, ws_port = ws_socket.getsockname()[:2]

        manager = SpriteProxyTunnelManager()
        base_url = await manager.ensure_tunnel(
            api_base_url=f"http://{ws_host}:{ws_port}",
            api_token="sprite-token",
            sprite_name="sprite-app-1",
            remote_host="127.0.0.1",
            remote_port=4141,
        )
        same_base_url = await manager.ensure_tunnel(
            api_base_url=f"http://{ws_host}:{ws_port}",
            api_token="sprite-token",
            sprite_name="sprite-app-1",
            remote_host="127.0.0.1",
            remote_port=4141,
        )

        assert same_base_url == base_url

        parsed = urlparse(base_url)
        reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
        try:
            writer.write(b"ping")
            await writer.drain()
            echoed = await asyncio.wait_for(reader.readexactly(len(b"reply:ping")), timeout=2.0)
        finally:
            writer.close()
            await writer.wait_closed()

        assert echoed == b"reply:ping"
        assert received_payloads == [b"ping"]
        assert seen_auth_headers == ["Bearer sprite-token"]
        assert seen_paths == ["/v1/sprites/sprite-app-1/proxy"]
    finally:
        server.close()
        await server.wait_closed()
