# Embed SDK, Platform SDK, and Future Agents SDK Layering Strategy

Last Updated: 2026-03-18

## Purpose

This document summarizes the chat discussion about the current role of `@agents24/embed-sdk`, how it differs from OpenAI's Agents SDK, and the possible SDK/product layers Talmudpedia could expose over time.

This is a strategy summary, not a canonical product spec.

## Current State

Talmudpedia now has a published npm package:

- `@agents24/embed-sdk`

Its current role is narrow and server-oriented:

- authenticate to the embed runtime with a tenant API key
- stream a published embedded agent
- list threads
- fetch thread details

The package is an integration surface for customers embedding an already-published agent into their own application backend.

It is not currently:

- an agent authoring SDK
- a control-plane/admin SDK
- a local agent framework
- a browser SDK

## What `@agents24/embed-sdk` Allows Today

Today the SDK lets a customer backend:

- call `POST /public/embed/agents/{agent_id}/chat/stream`
- call `GET /public/embed/agents/{agent_id}/threads`
- call `GET /public/embed/agents/{agent_id}/threads/{thread_id}`
- receive typed `run-stream.v2` envelopes
- persist and reuse `threadId`

This means the customer can build:

- a standalone web app around a published agent
- a backend-for-frontend that proxies the runtime
- a thread/history experience keyed by `external_user_id`

This does not allow the customer to create or manage platform resources such as:

- agents
- tools
- artifacts
- knowledge stores
- credentials
- models
- publish flows

## Comparison With OpenAI's Agents SDK

The key distinction from OpenAI's Agents SDK is that OpenAI's SDK is much closer to an agent-definition and agent-execution framework.

OpenAI's Agents SDK supports defining an agent in code with concepts such as:

- instructions
- model choice
- tools
- handoffs
- guardrails
- structured outputs
- hooks
- context injection
- orchestration behavior

Talmudpedia's current `@agents24/embed-sdk` does not expose that kind of code-authored agent surface. It assumes:

- the agent already exists on Talmudpedia
- the agent is already published
- the runtime behavior is already defined inside the platform

So the current Talmudpedia embed SDK is not equivalent to OpenAI's Agents SDK. It is more like a remote runtime client for an already-defined hosted agent.

## Core Strategic Question Identified In Chat

The real strategic question is not whether the embed SDK should grow to support resource creation.

The deeper question is:

- should Talmudpedia ever expose its internal agent framework as a public SDK so customers can define and run agents outside the platform?

This matters because OpenAI can safely expose a more open SDK layer while still monetizing usage through their model APIs. Talmudpedia is not itself the model provider, so exposing too much of the internal runtime could weaken platform lock-in.

## Recommended Strategic Position From The Discussion

The recommended default position is:

- keep `@agents24/embed-sdk` narrow
- add a separate control-plane/platform SDK for resource creation and management
- do not rush to expose the full internal agent framework for local execution

The reasoning:

- embed runtime and control-plane APIs have different auth and trust models
- embed runtime is a lightweight integration surface
- control-plane APIs are admin/build surfaces
- local/full external execution would create platform-fragmentation and support risk

This leads to a strong principle:

- portable control plane, non-portable execution

Meaning:

- customers should be able to define and manage resources in code
- execution should remain platform-native by default

## Alternative Lock-In Model Discussed

A second important idea from the chat was that Talmudpedia does not need to be a model provider in order to make the platform the required execution layer.

Possible positioning:

- Talmudpedia is the agent operating layer

Under that model, even if customers author agents or workflows in code in the future, the SDK/runtime still depends on Talmudpedia backend services for:

- model routing
- credential brokering
- tool execution
- artifact execution
- knowledge-store access
- thread/history persistence
- tracing and observability
- guardrails and policies
- publish/version resolution
- tenant security and metering

This would allow a richer future SDK without giving customers a fully portable local runtime.

## SDK Layers That Came Out Of The Discussion

### Layer 1: `@agents24/embed-sdk`

Purpose:

- runtime SDK for embedding published agents into customer-owned apps

Scope:

- stream runs
- list threads
- fetch thread details

Audience:

- customer backend developers integrating published agents

Execution:

- always through Talmudpedia embed runtime

### Layer 2: `@agents24/platform-sdk` or `@agents24/control-sdk`

Purpose:

- programmatic creation and management of platform resources

Likely domains:

- agents
- tools
- artifacts
- knowledge stores
- credentials
- models
- tenant API keys
- publish flows

Audience:

- developers and teams managing Talmudpedia resources in code

Execution:

- resource mutation and publishing through Talmudpedia backend APIs

This layer was identified as the highest-value next SDK after the current embed SDK.

### Layer 3: possible future `@agents24/agents-sdk`

Purpose:

- code-authored agents with a richer developer experience similar to the OpenAI Agents SDK

Important constraint from the discussion:

- this should not default to platform-independent local execution

If this layer is ever built, the safer version is:

- code-authored agents
- platform-executed runs
- Talmudpedia remains mandatory for runtime resources and execution

This would provide better developer ergonomics without giving away the core runtime moat.

## Maturity Upgrades For The Current Embed SDK

The chat also identified the likely maturity roadmap for `@agents24/embed-sdk` itself.

### Phase 1: transport maturity

- abort support
- timeout support
- retry controls where appropriate
- stronger input validation
- richer error metadata
- async iterator streaming in addition to callback streaming

### Phase 2: contract maturity

- discriminated event unions for known runtime events
- stricter backend contract tests
- semver discipline and clearer changelog/release policy
- compatibility guarantees for stream/event shapes

### Phase 3: integration maturity

- framework adapters or examples for Express, Next route handlers, Fastify, Hono, etc.
- observability hooks
- richer production cookbook documentation

## Main Product Decision Framed Clearly

The discussion concluded that the primary decision is not:

- "should the embed SDK support more endpoints?"

The primary decision is:

- "do we want Talmudpedia to expose a code-authored agents framework, and if yes, should it still require Talmudpedia backend execution?"

The current recommendation from the discussion is:

1. keep `@agents24/embed-sdk` narrow and runtime-focused
2. build a separate platform/control-plane SDK next
3. only later consider a richer agents SDK
4. if an agents SDK is built, prefer platform-executed rather than fully portable local execution

## Recommended Near-Term Next Step

The most coherent next product move is:

- build `@agents24/platform-sdk`

This gives customers programmability for creating and managing agents, tools, artifacts, and knowledge stores in code, while preserving Talmudpedia as the execution and governance layer.

That path improves developer adoption without prematurely weakening the platform boundary.
