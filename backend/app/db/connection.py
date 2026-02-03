import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

class MongoDatabase:
    client: Optional[AsyncIOMotorClient] = None
    db_name: str = os.getenv("MONGO_DB_NAME", "sefaria")

    @classmethod
    async def connect(cls):
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            logger.warning("MONGO_URI not found in environment. MongoDB features (Sefaria) may not work.")
            return
        cls.client = AsyncIOMotorClient(mongo_uri, uuidRepresentation='standard')
        print("Connected to MongoDB")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            print("Closed MongoDB connection")

    @classmethod
    def _get_db(cls):
        if cls.client is None:
            mongo_uri = os.getenv("MONGO_URI")
            if not mongo_uri:
                raise RuntimeError("MONGO_URI not set. Cannot access MongoDB.")
            cls.client = AsyncIOMotorClient(mongo_uri, uuidRepresentation='standard')
        return cls.client[cls.db_name]

    @classmethod
    def get_sefaria_collection(cls, collection_name: str):
        """
        Get a Sefaria-specific collection. 
        Only allows access to 'library_siblings' and 'library_search'.
        """
        ALLOWED_COLLECTIONS = {"library_siblings", "library_search", "texts", "index"}
        
        if collection_name not in ALLOWED_COLLECTIONS:
            raise ValueError(f"Access to collection '{collection_name}' is restricted. Only Sefaria collections are allowed via Mongo.")

        db = cls._get_db()
        return db[collection_name]
