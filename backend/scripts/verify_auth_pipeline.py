import asyncio
import httpx
import uuid
import jwt
import os
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

async def test_auth_pipeline():
    print("--- Starting Auth Pipeline Verification ---")
    
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "testpassword123"
    full_name = "Test User"

    print(f"1. Testing Registration: {email}")
    async with httpx.AsyncClient() as client:
        # Register
        try:
            reg_resp = await client.post(
                f"{BASE_URL}/auth/register",
                json={"email": email, "password": password, "full_name": full_name},
                timeout=30.0
            )
        except Exception as e:
            print(f"FAIL: Registration request failed with exception: {type(e).__name__}: {e}")
            return
            
        if reg_resp.status_code != 200:
            print(f"FAIL: Registration failed with {reg_resp.status_code}: {reg_resp.text}")
            return
        
        user_data = reg_resp.json()
        print(f"SUCCESS: Registered user {user_data['id']}")
        print(f"Context: Tenant={user_data.get('tenant_id')}, OrgUnit={user_data.get('org_unit_id')}")
        
        tenant_id = user_data.get('tenant_id')
        org_unit_id = user_data.get('org_unit_id')
        
        if not tenant_id or not org_unit_id:
            print("FAIL: Tenant or OrgUnit missing in registration response")
            return

        print("2. Testing Login")
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            data={"username": email, "password": password}
        )
        if login_resp.status_code != 200:
            print(f"FAIL: Login failed with {login_resp.status_code}: {login_resp.text}")
            return
        
        token_data = login_resp.json()
        token = token_data['access_token']
        print("SUCCESS: Login successful, token received")

        print("3. Verifying JWT Claims")
        # Note: We don't have the SECRET_KEY here easily unless we read it from .env
        # But we can inspect the payload without verification for this test
        payload = jwt.decode(token, options={"verify_signature": False})
        print(f"Payload: {payload}")
        
        if payload.get("tenant_id") != tenant_id:
            print(f"FAIL: tenant_id in token ({payload.get('tenant_id')}) does not match registration ({tenant_id})")
        else:
            print("SUCCESS: tenant_id match")
            
        if payload.get("org_unit_id") != org_unit_id:
            print(f"FAIL: org_unit_id in token ({payload.get('org_unit_id')}) does not match registration ({org_unit_id})")
        else:
            print("SUCCESS: org_unit_id match")

        print("4. Testing /me endpoint")
        me_resp = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        if me_resp.status_code != 200:
            print(f"FAIL: /me failed with {me_resp.status_code}: {me_resp.text}")
            return
        
        me_data = me_resp.json()
        print(f"SUCCESS: /me returned context: Tenant={me_data.get('tenant_id')}, OrgUnit={me_data.get('org_unit_id')}")
        
        if me_data.get('tenant_id') == tenant_id and me_data.get('org_unit_id') == org_unit_id:
            print("FINAL SUCCESS: All auth pipeline checks passed!")
        else:
            print("FAIL: /me context mismatch")

if __name__ == "__main__":
    asyncio.run(test_auth_pipeline())
