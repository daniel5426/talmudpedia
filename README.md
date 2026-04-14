# TalmudPedia: Enterprise AI Agent & RAG Platform

Last Updated: 2026-04-14

## Overview
A foundational AI Development and Execution OS for building, governing, and operating sophisticated AI systems at scale. Provides a unified control plane for models, data, tools, and reasoning workflows while remaining vendor-agnostic.

## Structure
*   `/frontend-reshet`: Next.js 14 application (React, Tailwind, Shadcn/UI).
*   `/backend`: FastAPI application (Python, LangGraph, PostgreSQL).

## Getting Started

### Frontend
```bash
cd frontend-reshet
pnpm install
pnpm dev
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Local apps-builder queues are auto-bootstrapped with a reloadable Celery supervisor when `DB_TARGET=local` and queue automation is enabled. To run the worker manually with the same behavior:

```bash
cd backend
python run_celery.py --reload worker -Q apps_build,agent_runs,default,ingestion,embedding -l info
```
