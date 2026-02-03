import asyncio
import os
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), "backend", ".env"))

from app.db.postgres.models.rag import PipelineJob, PipelineJobStatus, PipelineStepExecution

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def check_jobs():
    async with async_session() as session:
        jobs = (await session.execute(
            select(PipelineJob)
            .order_by(PipelineJob.created_at.desc())
            .limit(5)
        )).scalars().all()
        
        for job in jobs:
            print(f"Job: {job.id} Status: {job.status}")
            if job.error_message:
                print(f"  Error: {job.error_message}")
            
            steps = (await session.execute(
                select(PipelineStepExecution)
                .where(PipelineStepExecution.job_id == job.id)
                .order_by(PipelineStepExecution.execution_order)
            )).scalars().all()
            
            for step in steps:
                print(f"  Step: {step.step_id} ({step.operator_id}) Status: {step.status}")
                if step.error_message:
                    print(f"    Error: {step.error_message}")
            print("-" * 20)

if __name__ == '__main__':
    asyncio.run(check_jobs())
