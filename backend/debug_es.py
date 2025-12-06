import os
import asyncio
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def main():
    client = AsyncElasticsearch(
        os.getenv("ELASTICSEARCH_URL"),
        api_key=os.getenv("ELASTICSEARCH_API_KEY")
    )
    
    index_name = "reshet"
    
    print(f"Checking index: {index_name}")
    try:
        exists = await client.indices.exists(index=index_name)
        print(f"Index exists: {exists}")
        
        if exists:
            count = await client.count(index=index_name)
            print(f"Document count: {count['count']}")
            
            if count['count'] > 0:
                print("Fetching sample document...")
                response = await client.search(index=index_name, size=1)
                print(response['hits']['hits'][0])
                
                print("\nSearching for 'Edom'...")
                response = await client.search(
                    index=index_name,
                    body={
                        "query": {
                            "multi_match": {
                                "query": "Edom",
                                "fields": ["text", "ref", "book"]
                            }
                        }
                    }
                )
                print(f"Found {response['hits']['total']['value']} matches for 'Edom'")
                for hit in response['hits']['hits']:
                    print(f"Match: {hit['_id']} (Score: {hit['_score']})")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
