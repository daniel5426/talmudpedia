# Rabbinic AI Platform (The "Apyon")

## Overview
A comprehensive AI-powered interface for Rabbinic literature, featuring a "Rav" agent, interactive Chavruta mode, and deep semantic search.

## Structure
*   `/frontend`: Next.js 14 application (React, Tailwind, Shadcn/UI).
*   `/backend`: FastAPI application (Python, LangChain, Pinecone).

## Getting Started

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
