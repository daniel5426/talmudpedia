# Voice Runtime Current State

Last Updated: 2026-03-10

This document is the canonical current-state architecture overview for voice mode.

## Purpose

Voice mode provides realtime speech-oriented interaction through a provider registry and websocket entrypoint.

## Current Runtime Shape

Current main layers:
- websocket entrypoint in `backend/app/api/routers/voice_ws.py`
- provider registry in `backend/app/services/voice/registry.py`
- provider implementations under `backend/app/services/voice/`

The current router is mounted under:
- `/api/voice/session`

## Current Behavior

- the websocket accepts `chat_id`, `token`, and `provider`
- the backend decodes the bearer-like token from query params for user identity
- a chat can be created automatically when missing
- the selected provider session is resolved from the registry
- the provider session handles upstream provider transport and downstream frontend messages

## Current Provider Model

The voice provider registry maps provider names to `BaseVoiceSession` implementations.

Current verified implementation:
- Gemini voice session

The Gemini session currently handles:
- external provider websocket setup
- audio streaming
- user text submission
- provider receive loop
- chat/message persistence
- retrieval-tool integration via `RetrievalService`

## Important Current Constraint

Voice auth/tenant resolution is not yet aligned with the stricter principal model used by many newer secure routes.

Current behavior in `voice_ws.py` still includes fallback-to-first-tenant logic when user context is missing or incomplete. That should be treated as current implementation reality, not as the desired long-term security posture.

## Canonical Implementation References

- `backend/app/api/routers/voice_ws.py`
- `backend/app/services/voice/base.py`
- `backend/app/services/voice/registry.py`
- `backend/app/services/voice/gemini_session.py`
