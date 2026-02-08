from types import SimpleNamespace

from artifacts.builtin.platform_sdk import handler


def test_platform_sdk_fetch_catalog_uses_internal_delegation(monkeypatch):
    captured_posts = []

    def fake_post(url, json=None, headers=None, timeout=None):
        captured_posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/internal/auth/delegation-grants"):
            payload = {"grant_id": "9e9d9a1b-212f-4af1-92a1-f4b1c8ed5710", "effective_scopes": ["pipelines.catalog.read"]}
        elif url.endswith("/internal/auth/workload-token"):
            payload = {"token": "delegated-token"}
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return SimpleNamespace(status_code=200, json=lambda: payload, raise_for_status=lambda: None)

    monkeypatch.setattr(handler.requests, "post", fake_post)
    monkeypatch.setattr(handler, "_fetch_catalog", lambda client, payload: {"ok": True})

    result = handler.execute(
        state={},
        config={},
        context={
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
    assert len(captured_posts) == 2
    assert captured_posts[0]["url"].endswith("/internal/auth/delegation-grants")
    assert captured_posts[1]["url"].endswith("/internal/auth/workload-token")
