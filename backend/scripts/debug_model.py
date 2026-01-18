import asyncio
import uuid
from sqlalchemy import select
from app.db.postgres.session import async_session
from app.db.postgres.models.registry import ModelRegistry

async def check_model():
    model_id = "5fa69220-eedd-4b42-8007-913c78d86fbc"
    async with async_session() as session:
        try:
            query = select(ModelRegistry).where(ModelRegistry.id == uuid.UUID(model_id))
            result = await session.execute(query)
            model = result.scalar_one_or_none()
            
            if model:
                print(f"Model Found: {model.name}")
                print(f"ID: {model.id}")
                print(f"Is Active: {model.is_active}")
                print(f"Tenant ID: {model.tenant_id}")
                print(f"Provider: {model.provider}")
            else:
                print(f"Model {model_id} NOT FOUND in database.")
                
        except Exception as e:
            print(f"Error checking model: {e}")

if __name__ == "__main__":
    asyncio.run(check_model())
