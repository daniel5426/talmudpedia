# Service Token Authentication

## Purpose
Service tokens enable **internal, platform-to-platform** calls that require admin-level access without exposing user credentials. They are short-lived JWTs scoped to a tenant and used by the Platform SDK and internal automation.

## When to Use
Use service tokens for:
- SDK calls from internal tools to admin endpoints
- Background services that need scoped tenant access

Do not use service tokens for:
- End-user browser or client traffic
- Third-party integrations (use user tokens)

## Token Claims
Service tokens include the following claims:
- `role`: "platform-service"
- `tenant_id`: UUID of the tenant
- `sub`: "platform-service" (default)
- `exp`: 5 minutes from issuance

## Signing Secret
Service tokens are signed with:
- `PLATFORM_SERVICE_SECRET`

If this environment variable is missing, service token minting will fail.

## Issuance
The token issuer lives in `backend/app/core/internal_token.py`:
- `create_service_token(tenant_id, subject="platform-service")`

Example payload:
```json
{
  "sub": "platform-service",
  "role": "platform-service",
  "tenant_id": "<tenant_uuid>",
  "exp": "<utc_timestamp>"
}
```

## Validation
Service tokens are validated by:
- `decode_service_token(token)`
- Dependency `get_current_service_caller`

Validation rules:
- Signature must match `PLATFORM_SERVICE_SECRET`
- `role` must equal `platform-service`
- `tenant_id` must be present

## Accepted Endpoints
Service tokens are accepted only for internal SDK flows:
- `GET /admin/pipelines/catalog`
- `POST /admin/pipelines/visual-pipelines`
- `POST /agents`

Endpoints that require a user or membership still enforce user auth.

## Example Usage
```bash
curl -H "Authorization: Bearer $SERVICE_TOKEN" \
  http://localhost:8000/admin/pipelines/catalog
```

## Security Notes
- Tokens are **short-lived** (5 minutes)
- Always include a tenant scope
- Never expose service tokens to clients or UI
