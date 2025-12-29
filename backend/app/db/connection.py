import os
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from urllib.parse import quote_plus

user = "daniel"
password = "Hjsjfk74jkffdDF"
ip = "155.138.219.192"
db = "sefaria"

uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db}?authSource=admin"

class MongoDatabase:
    client: Optional[AsyncIOMotorClient] = None
    db_name: str = "sefaria"

    @classmethod
    async def connect(cls):
        mongo_uri = os.getenv("MONGO_URI", uri)
        cls.client = AsyncIOMotorClient(mongo_uri)
        print(f"Connected to MongoDB at {mongo_uri}")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            print("Closed MongoDB connection")

    @classmethod
    def get_db(cls):
        if cls.client is None:
            raise Exception("Database not initialized. Call connect() first.")
        return cls.client[cls.db_name]

    @classmethod
    def get_collection(cls, collection_name: str):
        return cls.get_db()[collection_name]
