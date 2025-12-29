import httpx
import asyncio
import ssl

async def test_ssl_variants():
    urls = ["https://api.openai.com/v1/models"]
    
    # Try different contexts
    contexts = []
    
    # Standard context
    contexts.append(("Default", ssl.create_default_context()))
    
    # Force TLS 1.2
    ctx_12 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx_12.options |= ssl.OP_NO_TLSv1_3
    contexts.append(("Force TLS 1.2", ctx_12))
    
    # Very permissive
    ctx_permissive = ssl.create_default_context()
    ctx_permissive.check_hostname = False
    ctx_permissive.verify_mode = ssl.CERT_NONE
    contexts.append(("Permissive (No Verify)", ctx_permissive))

    for name, ctx in contexts:
        print(f"--- Testing: {name} ---")
        try:
            async with httpx.AsyncClient(verify=ctx) as client:
                r = await client.get(urls[0])
                print(f"Status: {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ssl_variants())
