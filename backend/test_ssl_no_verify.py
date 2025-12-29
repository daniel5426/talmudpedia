import httpx
import asyncio
import urllib3
urllib3.disable_warnings()

async def test():
    try:
        async with httpx.AsyncClient(verify=False) as client:
            r = await client.get("https://api.openai.com/v1/models")
            print(f"Status: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
