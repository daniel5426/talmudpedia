# Admin Monitoring Users Spec

Last Updated: 2026-03-19

This document defines the current admin monitoring contract for the `Users` surface.

## Purpose

The admin `Users` page is now a unified monitored-users view, not a platform-auth-only list.

It includes:
- platform users
- published app accounts
- embedded external users

## Monitored Actor Model

The backend derives a read-only monitored actor model from existing runtime/auth data.

Actor types:
- `platform_user`
- `published_app_account`
- `embedded_external_user`

Rules:
- platform users use their raw user UUID as `actor_id`
- unmapped app accounts use `app_account:<uuid>`
- embedded users use an agent-scoped derived id
- published app accounts with `global_user_id` merge into the matching platform user actor tenant-wide
- embedded users do not merge across agents

## Admin Route Contract

Current monitoring routes:
- `GET /admin/users`
- `GET /admin/users/{actor_id}`
- `GET /admin/users/{actor_id}/threads`

Current list/detail payloads expose at minimum:
- `actor_id`
- `actor_type`
- `display_name`
- `email`
- `avatar`
- `platform_user_id`
- `source_app_count`
- `last_activity_at`
- `threads_count`
- `token_usage`
- `is_manageable`

## Management Behavior

The page label remains `Users` for UI continuity.

Management behavior is mixed:
- platform-user rows remain manageable
- external/app/embed rows are monitoring-only and read-only

Platform-user-only mutations remain on the existing user-management endpoints.
