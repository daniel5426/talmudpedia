import asyncio
import aiohttp
import json

async def test_pages_before():
    base_url = "http://localhost:8000"
    # Test with a reference that should have previous pages
    ref = "Berakhot 2b"
    url = f"{base_url}/api/source/{ref}?pages_before=1&pages_after=0"
    
    print(f"Fetching {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"Error: {response.status}")
                print(await response.text())
                return
            
            data = await response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if 'pages' in data:
                print(f"Received {len(data['pages'])} pages.")
                for i, page in enumerate(data['pages']):
                    print(f"Page {i}: {page['ref']}")
            else:
                print("No 'pages' field in response.")

if __name__ == "__main__":
    asyncio.run(test_pages_before())
