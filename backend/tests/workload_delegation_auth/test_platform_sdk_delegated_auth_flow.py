from app.system_artifacts.platform_sdk import handler


def test_platform_sdk_fetch_catalog_uses_internal_delegation(monkeypatch):
    captured = {}

    async def fake_mint_token(*, scope_subset, audience):
        captured["scope_subset"] = list(scope_subset)
        captured["audience"] = audience
        return "delegated-token"

    monkeypatch.setattr(handler, "_fetch_catalog", lambda client, payload: ({"ok": True}, []))

    result = handler.execute(
        state={},
        config={},
        context={
            "auth": {"mint_token": fake_mint_token},
            "inputs": {
                "action": "fetch_catalog",
                "base_url": "http://localhost:8000",
                "token": "user-token",
                "tenant_id": "c291a7b4-9602-4556-a335-7bf1db3b3c69",
                "user_id": "f9f3854e-f490-4b00-bcd5-5d3068c29683",
            }
        },
    )

    assert result["context"]["result"] == {"ok": True}
    assert captured["scope_subset"] == ["pipelines.catalog.read"]
    assert captured["audience"] == "talmudpedia-internal-api"
