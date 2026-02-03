import asyncio
import httpx
import uuid
from typing import Dict, Any

BASE_URL = "http://localhost:8000/admin/artifacts"
TENANT_SLUG = "sefaria" # Assuming this exists or works

# Use a real token if needed, or assume dev environment without strict auth for now
# If auth is required, we might need a test user.
HEADERS = {}

async def test_artifact_workflow():
    async with httpx.AsyncClient(headers=HEADERS) as client:
        # 1. Create a Draft
        print("--- Step 1: Creating Draft ---")
        draft_payload = {
            "name": f"test_op_{uuid.uuid4().hex[:8]}",
            "display_name": "Test Op",
            "category": "normalization",
            "description": "Test description",
            "input_type": "raw_documents",
            "output_type": "normalized_documents",
            "python_code": "def execute(context): return context.input_data",
            "config_schema": [
                {"name": "test_param", "type": "string", "required": True}
            ]
        }
        resp = await client.post(f"{BASE_URL}?tenant_slug={TENANT_SLUG}", json=draft_payload)
        if resp.status_code != 200:
            print(f"Failed to create draft: {resp.text}")
            return
        
        draft = resp.json()
        draft_id = draft["id"]
        print(f"Created Draft ID: {draft_id}")

        # 2. Promote to File
        print("\n--- Step 2: Promoting to File ---")
        promote_payload = {
            "namespace": "custom",
            "version": "1.0.0"
        }
        resp = await client.post(f"{BASE_URL}/{draft_id}/promote?tenant_slug={TENANT_SLUG}", json=promote_payload)
        if resp.status_code != 200:
            print(f"Failed to promote: {resp.text}")
        else:
            print(f"Promotion Result: {resp.json()}")
            promoted_id = resp.json()["artifact_id"]

        # 3. Check List (Should NOT see the draft, SHOULD see the promoted)
        print("\n--- Step 3: Verifying List ---")
        resp = await client.get(f"{BASE_URL}?tenant_slug={TENANT_SLUG}")
        artifacts = resp.json()
        
        draft_found = any(a["id"] == draft_id for a in artifacts)
        promoted_found = any(a["id"] == promoted_id for a in artifacts)
        
        print(f"Draft still in list? {draft_found} (Expected: False)")
        print(f"Promoted artifact in list? {promoted_found} (Expected: True)")

        # 4. Update the Promoted Artifact
        print("\n--- Step 4: Updating Promoted Artifact ---")
        update_payload = {
            "display_name": "Updated Test Op",
            "python_code": "def execute(context): return 'updated'",
            "config_schema": [
                {"name": "new_param", "type": "integer", "required": False}
            ]
        }
        # Note: promoted_id likely contains a slash (custom/test_op_...)
        # We need to ensure the client handles this or encode it
        # FastAPI with :path handles it if passed as part of the URL
        resp = await client.put(f"{BASE_URL}/{promoted_id}?tenant_slug={TENANT_SLUG}", json=update_payload)
        if resp.status_code != 200:
            print(f"Failed to update: {resp.status_code} {resp.text}")
        else:
            updated = resp.json()
            print(f"Updated Display Name: {updated['display_name']}")
            print(f"Updated Config Schema: {updated['config_schema']}")

        # 5. Delete the Promoted Artifact
        print("\n--- Step 5: Deleting Promoted Artifact ---")
        resp = await client.delete(f"{BASE_URL}/{promoted_id}?tenant_slug={TENANT_SLUG}")
        if resp.status_code != 200:
            print(f"Failed to delete: {resp.status_code} {resp.text}")
        else:
            print("Successfully deleted promoted artifact")

if __name__ == "__main__":
    asyncio.run(test_artifact_workflow())
