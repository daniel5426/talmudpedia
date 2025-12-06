import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from dotenv import load_dotenv
load_dotenv("backend/.env")

async def check_shape():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["talmudpedia"]
    
    # Check Genesis
    genesis = await db["index"].find_one({"title": "Genesis"})
    if genesis:
        print("Genesis shape:", genesis.get("shape"))
        print("Genesis shape type:", type(genesis.get("shape")))
        if genesis.get("shape"):
            print("First element:", genesis["shape"][0] if len(genesis["shape"]) > 0 else "empty")
    
    # Check a Talmud book
    berachot = await db["index"].find_one({"title": "Berakhot"})
    if berachot:
        print("\nBerakhot shape:", berachot.get("shape"))
        print("Berakhot categories:", berachot.get("categories"))

if __name__ == "__main__":
    asyncio.run(check_shape())
