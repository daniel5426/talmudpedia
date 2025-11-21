import asyncio
import aiohttp
import json

async def test_pages_before_2():
    base_url = "http://localhost:8000"
    # Test with a reference that should have previous pages
    ref = "Berakhot 2b"
    url = f"{base_url}/api/source/{ref}?pages_before=2&pages_after=2"
    
    print(f"Fetching {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"Error: {response.status}")
                print(await response.text())
                return
            
            data = await response.json()
            # print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if 'pages' in data:
                print(f"Received {len(data['pages'])} pages.")
                print(f"Main Page Index: {data.get('main_page_index')}")
                
                for i, page in enumerate(data['pages']):
                    is_main = i == data.get('main_page_index')
                    marker = "*" if is_main else " "
                    print(f"{marker} Page {i}: {page['ref']} (Highlight Index: {page.get('highlight_index')})")
            else:
                print("No 'pages' field in response.")

if __name__ == "__main__":
    asyncio.run(test_pages_before_2())
