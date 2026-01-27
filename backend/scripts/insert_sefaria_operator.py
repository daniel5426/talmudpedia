import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load env from backend/.env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
# Handle postgresql:// -> postgresql+asyncpg://
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL, 
    echo=True,
    connect_args={"statement_cache_size": 0}
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

TENANT_ID = "d503d6dd-2b78-4768-95ab-4c6c84a2f194"

async def insert_sefaria_operator():
    with open("/Users/danielbenassaya/.gemini/antigravity/brain/fbd225cf-3511-4ea4-836d-b64c7a91fe0c/sefaria_operator.py", "r") as f:
        python_code = f.read()

    config_schema = [
        {
            "name": "index_title",
            "field_type": "string",
            "required": True,
            "description": "The title of the Sefaria book to ingest",
            "placeholder": "Mishnah Berakhot"
        },
        {
            "name": "limit",
            "field_type": "integer",
            "required": False,
            "default": 10,
            "description": "Maximum number of segments to fetch",
            "min_value": 1,
            "max_value": 1000
        },
        {
            "name": "version",
            "field_type": "string",
            "required": False,
            "default": "primary",
            "description": "Which version of the text to fetch"
        }
    ]

    async with AsyncSessionLocal() as session:
        # Check if already exists
        result = await session.execute(
            text("SELECT id FROM custom_operators WHERE tenant_id = :tid AND name = :name"),
            {"tid": TENANT_ID, "name": "sefaria_source"}
        )
        existing = result.fetchone()

        if existing:
            print("Operator 'sefaria_source' already exists. Updating code...")
            await session.execute(
                text("UPDATE custom_operators SET python_code = :code, config_schema = :schema, display_name = :dname WHERE id = :id"),
                {
                    "code": python_code,
                    "schema": json.dumps(config_schema),
                    "dname": "Sefaria Source",
                    "id": existing[0]
                }
            )
        else:
            print("Creating new 'sefaria_source' operator...")
            op_id = uuid.uuid4()
            await session.execute(
                text("""
                    INSERT INTO custom_operators 
                    (id, tenant_id, name, display_name, category, description, python_code, input_type, output_type, config_schema, version, is_active, created_at, updated_at) 
                    VALUES 
                    (:id, :tid, :name, :dname, :cat, :desc, :code, :in, :out, :schema, :ver, :active, NOW(), NOW())
                """),
                {
                    "id": op_id,
                    "tid": TENANT_ID,
                    "name": "sefaria_source",
                    "dname": "Sefaria Source",
                    "cat": "source",
                    "desc": "Custom operator to fetch texts from Sefaria API",
                    "code": python_code,
                    "in": "none",
                    "out": "raw_documents",
                    "schema": json.dumps(config_schema),
                    "ver": "1.0.0",
                    "active": True
                }
            )
        
        await session.commit()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(insert_sefaria_operator())
