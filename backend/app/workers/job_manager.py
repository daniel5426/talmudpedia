import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import asyncio

import redis.asyncio as redis
from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProgress(BaseModel):
    job_id: str
    status: JobStatus
    current_stage: str = "initializing"
    total_documents: int = 0
    processed_documents: int = 0
    total_chunks: int = 0
    upserted_chunks: int = 0
    failed_chunks: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    percent_complete: float = 0.0


class JobManager:
    
    _redis: Optional[redis.Redis] = None
    _pubsub_clients: Dict[str, Any] = {}
    
    JOB_KEY_PREFIX = "rag:job:"
    JOB_CHANNEL_PREFIX = "rag:job:updates:"
    JOBS_LIST_KEY = "rag:jobs:list"
    
    def __init__(self, redis_url: str = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    async def _get_redis(self) -> redis.Redis:
        if JobManager._redis is None:
            JobManager._redis = redis.from_url(self._redis_url, decode_responses=True)
        return JobManager._redis
    
    def _job_key(self, job_id: str) -> str:
        return f"{self.JOB_KEY_PREFIX}{job_id}"
    
    def _channel_key(self, job_id: str) -> str:
        return f"{self.JOB_CHANNEL_PREFIX}{job_id}"
    
    async def create_job(self, job_id: str, index_name: str, source_type: str, **kwargs) -> JobProgress:
        r = await self._get_redis()
        
        progress = JobProgress(
            job_id=job_id,
            status=JobStatus.PENDING,
            current_stage="queued",
            **kwargs
        )
        
        await r.hset(self._job_key(job_id), mapping={
            "data": progress.model_dump_json(),
            "index_name": index_name,
            "source_type": source_type,
            "created_at": datetime.utcnow().isoformat()
        })
        
        await r.lpush(self.JOBS_LIST_KEY, job_id)
        await r.ltrim(self.JOBS_LIST_KEY, 0, 999)
        
        return progress
    
    async def update_progress(self, job_id: str, **updates) -> Optional[JobProgress]:
        r = await self._get_redis()
        key = self._job_key(job_id)
        
        data = await r.hget(key, "data")
        if not data:
            return None
        
        progress_dict = json.loads(data)
        progress_dict.update(updates)
        
        if progress_dict.get("total_documents", 0) > 0:
            progress_dict["percent_complete"] = min(
                100.0,
                (progress_dict.get("processed_documents", 0) / progress_dict["total_documents"]) * 100
            )
        
        progress = JobProgress(**progress_dict)
        await r.hset(key, "data", progress.model_dump_json())
        
        await r.publish(self._channel_key(job_id), progress.model_dump_json())
        await r.publish(f"{self.JOB_CHANNEL_PREFIX}all", progress.model_dump_json())
        
        return progress
    
    async def get_progress(self, job_id: str) -> Optional[JobProgress]:
        r = await self._get_redis()
        data = await r.hget(self._job_key(job_id), "data")
        
        if not data:
            return None
        
        return JobProgress(**json.loads(data))
    
    async def list_jobs(self, limit: int = 50) -> List[JobProgress]:
        r = await self._get_redis()
        
        job_ids = await r.lrange(self.JOBS_LIST_KEY, 0, limit - 1)
        
        jobs = []
        for job_id in job_ids:
            progress = await self.get_progress(job_id)
            if progress:
                jobs.append(progress)
        
        return jobs
    
    async def mark_started(self, job_id: str) -> Optional[JobProgress]:
        return await self.update_progress(
            job_id,
            status=JobStatus.RUNNING,
            current_stage="starting",
            started_at=datetime.utcnow().isoformat()
        )
    
    async def mark_completed(self, job_id: str, **stats) -> Optional[JobProgress]:
        return await self.update_progress(
            job_id,
            status=JobStatus.COMPLETED,
            current_stage="completed",
            completed_at=datetime.utcnow().isoformat(),
            percent_complete=100.0,
            **stats
        )
    
    async def mark_failed(self, job_id: str, error_message: str) -> Optional[JobProgress]:
        return await self.update_progress(
            job_id,
            status=JobStatus.FAILED,
            current_stage="failed",
            error_message=error_message,
            completed_at=datetime.utcnow().isoformat()
        )
    
    async def subscribe_to_job(self, job_id: str):
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(self._channel_key(job_id))
        return pubsub
    
    async def subscribe_to_all_jobs(self):
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"{self.JOB_CHANNEL_PREFIX}all")
        return pubsub


job_manager = JobManager()
