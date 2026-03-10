# Admin Stats Spec

Last Updated: 2026-03-10

This document is the canonical product/specification overview for the admin stats surface.

## Purpose

The admin stats surface provides tenant-scoped operational metrics for:
- overview
- RAG
- agents
- resources

## Current Endpoint

Current live backend path:
- `GET /admin/stats/summary`

This corrects older docs that referenced `/api/v1/admin/stats/summary`.

## Current Parameters

- `section`
- `days`
- `start_date`
- `end_date`

Current section values:
- `overview`
- `rag`
- `agents`
- `resources`

## Current Access Model

The backend currently uses a tenant context derived from the current user’s membership path inside the stats router.

This means the stats surface is tenant-scoped, but it does not yet use the newer shared principal/scope dependency pattern used by many other control-plane routes.

## Current Metric Families

### Overview

Current overview metrics include:
- users
- chats/messages
- token usage
- top users
- top models

### RAG

Current RAG metrics include:
- knowledge store summaries
- pipeline counts
- job duration and failure summaries

### Agents

Current agent metrics include:
- run counts and status trends
- token usage
- duration and queue metrics
- top agents and failure summaries

### Resources

Current resource metrics include:
- tools
- models
- provider bindings
- artifacts

## Current Frontend Surface

Current frontend page:
- `frontend-reshet/src/app/admin/stats/page.tsx`

The frontend uses centralized service/types under `frontend-reshet/src/services/`.

## Canonical Implementation References

- `backend/app/api/routers/stats.py`
- `backend/app/api/schemas/stats.py`
