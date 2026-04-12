# Tenant Plan Payments Feasibility Report

Last Updated: 2026-04-12

## Question

How hard would it be to let a tenant:

- create an agent
- expose it through a published app and/or external embedded app
- define paid plans
- use resource-policy-based limits as the plan enforcement layer
- require end users to pay to move from plan A to plan B

## Short Answer

Medium-to-hard.

Why:

- the platform already has a good entitlement enforcement base
- but it does not have billing, subscriptions, checkout, invoices, webhook handling, or plan lifecycle
- and the current resource-policy model is not yet a full customer-plan model

Best estimate:

- MVP for paid upgrades on top of existing runtime enforcement: about 3 to 5 weeks
- production-ready billing system with self-serve plan management, retries, dunning, admin tooling, and clean edge-case handling: about 6 to 10+ weeks

## What Already Exists

### 1. Runtime enforcement primitives already exist

The platform already enforces access and quotas at runtime through resource policies.

Relevant code/docs:

- `backend/app/services/resource_policy_service.py`
- `backend/app/services/resource_policy_quota_service.py`
- `backend/app/db/postgres/models/resource_policies.py`
- `docs/design-docs/auth_current.md`

Current supported principal types:

- tenant user
- published app account
- embedded external user

That is important because your monetization target is exactly the end user of:

- a published app
- an embedded agent integration

### 2. Default policy attachment already exists

You can already attach default policy sets to:

- a published app via `PublishedApp.default_policy_set_id`
- an embedded agent via `Agent.default_embed_policy_set_id`

Relevant code:

- `backend/app/db/postgres/models/published_apps.py`
- `backend/app/db/postgres/models/agents.py`
- `backend/app/api/routers/resource_policies.py`

This means the system already has a place to say:

- new users of this app start on the free/basic plan

### 3. Per-user override assignment already exists

Resource-policy assignments already support:

- published app account specific assignment
- embedded external user specific assignment

This is the core mechanic needed for “upgrade this user from plan A to plan B”.

### 4. Quota-aware execution already exists

Before a run starts, execution already reserves and enforces:

- general usage quotas
- resource-policy model quotas

Relevant code:

- `backend/app/agent/execution/service.py`
- `backend/app/services/usage_quota_service.py`
- `backend/app/services/resource_policy_quota_service.py`

This means the runtime side is already in good shape for “this plan allows X”.

### 5. Admin UI for resource policies already exists

There is already an admin resource-policies page and service layer.

Relevant paths:

- `frontend-reshet/src/app/admin/resource-policies/page.tsx`
- `frontend-reshet/src/__tests__/resource_policy_sets/`

That reduces implementation scope for internal/admin plan configuration.

## What Is Missing

### 1. No billing/subscription system exists

The repo explicitly says published apps do not yet include billing/subscriptions.

Relevant doc:

- `docs/product-specs/published_apps_spec.md`

Missing pieces:

- checkout
- payment provider integration
- subscriptions
- invoices/receipts
- webhook processing
- failed payment handling
- renewals/cancellations
- trial/grace-period rules

### 2. Resource policies are not yet “plans”

Current resource-policy rules support:

- `ALLOW`
- `QUOTA`

Current quota support is limited to:

- resource type `MODEL`
- unit `TOKENS`
- window `MONTHLY`

Relevant code:

- `backend/app/services/resource_policy_service.py`
- `backend/app/db/postgres/models/resource_policies.py`

So today a policy can mean:

- allow these models/tools/agents/knowledge stores
- cap this model to N monthly tokens

But it cannot natively express richer commercial plan concepts like:

- monthly seat count
- request count limits across all models
- feature flags
- branded app features
- attachment/storage limits
- “can use app A and app B under one subscription”

### 3. No first-class customer subscription entity exists

Today entitlements are attached to runtime principals, not to a billing/customer domain model.

That means there is no canonical entity for:

- billing customer
- active subscription
- purchased plan
- subscription status
- renewal state
- last successful payment

Without that layer, plan changes would be hard to audit and hard to synchronize safely with payments.

### 4. Embedded entitlements are scoped per agent + external user

For embedded runtime, assignment uniqueness is keyed by:

- tenant
- principal type
- embedded agent id
- external user id

Relevant code:

- `backend/app/db/postgres/models/resource_policies.py`

This is workable for “user X on embedded agent Y has premium”.

But it is weaker for broader commerce cases like:

- one paying customer should unlock multiple agents/apps
- one customer changes plan once and all related products should update

For that, you likely need a customer/account/subscription layer above current principal assignments.

### 5. Two quota systems exist

There is:

- `UsageQuotaService`
- `ResourcePolicyQuotaService`

That is not necessarily wrong, but for paid plans it creates product ambiguity:

- which limit is the actual commercial plan limit?
- which one is internal safety guardrail only?

If not clarified, billing behavior will be hard to explain and support.

## Feasibility By Surface

### Published apps

This is the easier path.

Why:

- published app accounts are first-class records
- resource-policy assignments already support `published_app_account`
- default policy set already exists on the app
- public runtime already converts quota failures into `429`

Relevant code:

- `backend/app/db/postgres/models/published_apps.py`
- `backend/app/api/routers/published_apps_public.py`

### Embedded / external apps

This is feasible, but a bit harder.

Why:

- runtime already supports per-`external_user_id` policy resolution
- default embed policy already exists on agents
- but the user identity belongs to the customer’s backend/app, not to Talmudpedia
- payment success must map correctly from external customer identity into `external_user_id`

Relevant docs/code:

- `docs/product-specs/embedded_agent_runtime_spec.md`
- `docs/references/embedded_agent_sdk_standalone_integration_guide.md`
- `backend/app/services/embedded_agent_runtime_service.py`

Important constraint:

- standalone/external apps must keep using `@agents24/embed-sdk` and the public embed contract
- do not solve billing by bypassing the public embed model with internal/admin API shortcuts

## Recommended Architecture

### Recommended plan model

Treat:

- billing plan = commercial source of truth
- resource policy set = runtime entitlement bundle

In other words:

- plan “Free” maps to policy set `free_plan_policy`
- plan “Pro” maps to policy set `pro_plan_policy`
- subscription change updates the user/account assignment to the mapped policy set

Do not make resource-policy tables themselves become the billing ledger.

### Recommended new domain objects

Add a billing domain with entities roughly like:

- billing_customers
- billing_products or tenant_sellable_plans
- billing_subscriptions
- billing_subscription_events
- billing_checkout_sessions
- billing_webhook_events

And a mapping layer:

- subscription plan -> policy_set_id

For embedded runtime, consider a reusable customer identity object instead of only raw `external_user_id`.

### Recommended runtime behavior

At user/app creation:

- assign the default free/basic policy

At payment success or upgrade:

- update the assignment to the higher-tier policy

At downgrade/cancel/payment failure:

- move assignment back to free/basic
- or mark the subscription state first and downgrade at period end

### Recommended product boundary

Phase 1 should support:

- admin-defined plans
- one payment provider
- monthly subscriptions
- plan-to-policy mapping
- upgrade/downgrade
- published apps and embedded apps

Phase 1 should not try to solve:

- multi-plan bundles
- add-ons
- coupons
- usage-based invoicing
- taxes across jurisdictions
- complex proration

## Main Risks

### 1. Identity mismatch in embedded apps

If the customer changes how it forms `external_user_id`, entitlements can break or duplicate.

You need a strict rule for:

- stable external customer identity

### 2. Plan semantics are currently too model-centric

If your commercial plans need more than model-token limits, current resource policies will need expansion.

Most likely future additions:

- request quotas
- attachment/storage quotas
- feature toggles
- app-level capability flags

### 3. Billing sync must be idempotent

Webhook replay, retries, delayed events, and payment failures can otherwise leave the wrong plan attached.

### 4. UX/admin complexity is mostly missing

Even if backend enforcement is straightforward, you still need product/admin surfaces for:

- creating sellable plans
- connecting plan to policy set
- seeing who is on which plan
- manual override
- subscription support/debug flows

## Estimated Difficulty

### Option A: lean MVP

Scope:

- one provider
- subscription checkout
- admin-created plans mapped to policy sets
- published app account upgrade path
- embedded external user upgrade path
- webhook-driven assignment updates

Difficulty:

- medium

Estimate:

- about 3 to 5 weeks

Main reason it is possible:

- runtime enforcement foundation already exists

### Option B: proper production billing system

Scope:

- everything in MVP
- robust customer/subscription domain
- retries/dunning
- better admin tooling
- auditability
- downgrade timing rules
- stronger embedded identity model
- tests around payment lifecycle edge cases

Difficulty:

- medium-high to high

Estimate:

- about 6 to 10+ weeks

## My Recommendation

Do it in two layers:

1. Build a thin billing domain that maps paid plans to resource policy sets.
2. Keep runtime enforcement in resource policies.

That is the cleanest fit with the current architecture.

Do not:

- mix billing state directly into runtime quota counters
- use payment provider state as the only source of truth inside runtime
- overextend the current resource-policy schema into a full commerce system

## Bottom Line

This is very doable.

The good news:

- the hard runtime entitlement hook already exists
- published-app and embedded-user principals already exist
- default and per-user policy assignment already exist

The hard part is not runtime blocking.

The hard part is building the missing billing/subscription domain cleanly enough that plan changes are reliable, auditable, and usable across both published apps and embedded apps.
