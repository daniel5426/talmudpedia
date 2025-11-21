import os
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

class MongoDatabase:
    client: Optional[AsyncIOMotorClient] = None
    db_name: str = "sefaria"

    @classmethod
    async def connect(cls):
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
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
