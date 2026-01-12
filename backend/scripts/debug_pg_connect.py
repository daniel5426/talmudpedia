import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

# Load env manually to verify path
env_path = os.path.join(backend_dir, ".env")
print(f"Loading env from: {env_path}")
load_dotenv(env_path)

def get_postgres_uri() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "talmudpedia")
    
    print(f"Connection Details: Host={host}, User={user}, DB={db}, Port={port}")
    return f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"

async def main():
    uri = get_postgres_uri()
    print(f"URI: {uri.replace(os.getenv('POSTGRES_PASSWORD', ''), '******')}")
    
    try:
        engine = create_async_engine(uri, echo=True)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(f"Connection successful! Result: {result.scalar()}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
