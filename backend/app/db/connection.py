import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

user = "daniel"
password = "Hjsjfk74jkffdDF"
ip = "155.138.219.192"
db_name = "sefaria"

uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"

class MongoDatabase:
    client: Optional[AsyncIOMotorClient] = None
    db_name: str = "sefaria"

    @classmethod
    async def connect(cls):
        mongo_uri = os.getenv("MONGO_URI", uri)
        cls.client = AsyncIOMotorClient(mongo_uri, uuidRepresentation='standard')
        print(f"Connected to MongoDB at {mongo_uri}")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            print("Closed MongoDB connection")

    @classmethod
    def get_db(cls):
        if cls.client is None:
            # Try to connect if not connected
            mongo_uri = os.getenv("MONGO_URI", uri)
            cls.client = AsyncIOMotorClient(mongo_uri, uuidRepresentation='standard')
        return cls.client[cls.db_name]

    @classmethod
    def get_sefaria_collection(cls, collection_name: str):
        """
        Get a Sefaria-specific collection. 
        Only allows access to 'library_siblings' and 'library_search'.
        """
        ALLOWED_COLLECTIONS = {"library_siblings", "library_search"}
        
        if collection_name not in ALLOWED_COLLECTIONS:
            raise ValueError(f"Access to collection '{collection_name}' is restricted. Only Sefaria collections are allowed via Mongo.")

        db = cls.get_db()
        return db[collection_name]
