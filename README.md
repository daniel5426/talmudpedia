# TalmudPedia: Enterprise AI Agent & RAG Platform

Last Updated: 2026-03-23

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
