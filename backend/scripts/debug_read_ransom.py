import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def read_ransom():
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"

    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/?authSource=admin"
    client = AsyncIOMotorClient(uri)
    
    db = client["READ__ME_TO_RECOVER_YOUR_DATA"]
    doc = await db["README"].find_one({})
    print(f"Ransom note: {doc}")

    client.close()

if __name__ == "__main__":
    asyncio.run(read_ransom())
