import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.workers.job_manager import job_manager

router = APIRouter()


@router.websocket("/jobs/{job_id}")
async def job_progress_websocket(websocket: WebSocket, job_id: str):
    await websocket.accept()
    
    try:
        progress = await job_manager.get_progress(job_id)
        if progress:
            await websocket.send_json(progress.model_dump())
        
        pubsub = await job_manager.subscribe_to_job(job_id)
        
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=30.0
                )
                
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if data:
                        await websocket.send_text(data)
                        
                        progress_data = json.loads(data)
                        if progress_data.get("status") in ["completed", "failed", "cancelled"]:
                            break
                
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe()
        except Exception:
            pass


@router.websocket("/jobs")
async def all_jobs_websocket(websocket: WebSocket):
    await websocket.accept()
    
    try:
        jobs = await job_manager.list_jobs(limit=20)
        await websocket.send_json({
            "type": "initial",
            "jobs": [job.model_dump() for job in jobs]
        })
        
        pubsub = await job_manager.subscribe_to_all_jobs()
        
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=30.0
                )
                
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if data:
                        await websocket.send_json({
                            "type": "update",
                            "job": json.loads(data)
                        })
                
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe()
        except Exception:
            pass
