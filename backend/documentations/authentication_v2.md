# Authentication & Authorization V2 (Hybrid Model)

This document describes the current state of authentication and authorization in the platform, following the "Hybrid Product-Led + Enterprise" architecture.

## 1. Core Architecture

We separate **Identity** (who you are) from **Access** (where you belong).

### 1.1 Data Model
The system relies on three core Postgres tables:

| Entity | Table | Description |
| :--- | :--- | :--- |
| **User** | `users` | **Global Identity**. Contains email, password hash, and system-level `role` (e.g., `admin`, `user`). |
| **Tenant** | `tenants` | **Workspace/Organization**. The isolated container for data (chats, docs, etc.). |
| **Membership** | `org_memberships` | **Link**. Connects a User to a Tenant with a specific `OrgRole` (e.g., `owner`, `admin`, `member`). |

### 1.2 Roles & Permissions

#### System Role (`User.role`)
Controls platform-wide access.
- `admin`: Superuser. Can see all data across *all* tenants.
- `user`: Standard user. Access is restricted by their Tenant Membership.

#### Organization Role (`OrgMembership.role`)
Controls access *within* a specific tenant.
- `owner`: Full control over the tenant. Can invite users, manage billing, and view audit logs.
- `admin`: Can manage users and view tenant analytics.
- `member`: Can create chats and access standard features.

## 2. Authentication Flow

### 2.1 Registration (Auto-Provisioning)
When a new user signs up (Email or Google SSO):
1.  **Identity Creation**: A `User` record is created.
2.  **Tenant Provisioning**: A new `Tenant` (e.g., "Daniel's Organization") is automatically created.
3.  **Owner Assignment**: The user is linked to this new Tenant via `OrgMembership` with `role='owner'`.

### 2.2 Login & Context
On login, we generate a JWT `access_token` that carries the user's primary context.

**JWT Payload:**
```json
{
  "sub": "user_uuid",
  "tenant_id": "current_tenant_uuid",
  "org_role": "owner"
}
```

*Note: The backend `auth.py` router prioritizes this token payload but includes a fallback lookup to the database if `org_role` is missing (for legacy or switched contexts).*

## 3. Security Implementation

### 3.1 Frontend (`Next.js`)
- **State Management**: `useAuthStore` persists the user and their `org_role`.
- **Auto-Refresh**: The `<AuthRefresher />` component (in `layout.tsx`) calls `/auth/me` on app load to ensure permission headers are up-to-date.
- **Route Guards**:
    - **Admin Space**: Protected in `admin/layout.tsx`. Redirects users unless they are System Admins OR Tenant Owners/Admins.

### 3.2 Backend (`FastAPI`)
- **API Security**: Endpoints use `Dependency(get_current_user)`.
- **Admin & Scoping**: The `/admin` router (`admin.py`) is fully **Tenant-Scoped**:
    - Queries `chats`, `users`, and `messages` tables in Postgres.
    - If the caller is a **System Admin**, they see global data.
    - If the caller is a **Tenant Owner**, a filter `WHERE tenant_id = :cid` is applied to all queries.

## 4. Current Status
- [x] **Postgres Migration**: All auth and admin data now lives in Postgres (replacing Mongo for these features).
- [x] **Secure Admin Dashboard**: Live, scoped analytics are functional.
- [x] **Hybrid Roles**: Users can be `owners` of their own space and potentially `members` of others (multi-tenancy ready).
