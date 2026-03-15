# Client Exposure Copilot POC Spec

## Overview

The Client Exposure Copilot is a Tier 2-facing AI agent for Prico clients and internal relationship managers. Its purpose is to let a CFO, treasurer, or Prico analyst ask plain-language questions about a client's transactions, hedge activity, bank concentration, FX context, and current uncovered exposure without needing to know SQL or raw table structures.

This POC is designed to demonstrate a premium, decision-support experience rather than a back-office control tool. It should feel like an on-prem treasury copilot built on top of Prico's internal deal and exposure data.

## Goal

Deliver a read-only AI copilot that can:

- answer natural-language questions about a client's recent deals and exposures
- explain individual deals in business language
- provide market context for the deal date
- summarize concentration by bank and currency
- optionally compare known future obligations against existing hedge activity

## Why This POC

This POC aligns with the strategy of moving into Tier 2: customer dashboards and natural-language querying.

It is a strong demo because it shows:

- immediate business value to CFOs and treasurers
- a visible AI experience, not just internal automation
- Prico's domain authority embedded in software
- a path toward future netting, strategy suggestions, and direct execution flows

## Target Users

- CFO of a client company
- Treasurer or finance manager at a client
- Prico relationship manager
- Prico dealing room / analyst team

## Core User Jobs

- understand what deals a client has executed recently
- understand which banks and currencies the client is most exposed to
- inspect one deal in detail with timeline and pricing context
- identify unusual pricing or missing operational context
- understand what future obligations remain uncovered

## POC User Stories

- As a CFO, I want to ask "What did we do in EUR this month?" and get a clear answer with totals and deal details.
- As a treasurer, I want to ask "Which banks are we most concentrated in right now?" and get a ranked answer.
- As a Prico analyst, I want to click a deal and see a structured explanation of what happened.
- As a finance user, I want to understand whether a deal's pricing was close to market at the time it was executed.
- As a client user, I want to upload future obligations and see how much of them are already covered by existing trades.

## POC Scope

### In Scope

- natural-language query interface over a constrained semantic layer
- client-level filtering
- recent deals summary
- bank concentration summary
- currency concentration summary
- deal detail explainer
- market context on deal date
- simple uploaded-obligation netting view
- read-only data access

### Out of Scope

- direct execution or order transmission
- automatic hedge recommendations
- reconciliation of bank confirmations
- free-form SQL generation for end users
- autonomous actions
- broad cross-client analytics without access controls

## Core Experience

### 1. Ask In Plain Language

The user can ask questions such as:

- "Show me all EUR deals for client 9192 this quarter."
- "Which banks is this client most exposed to?"
- "Explain deal 200462."
- "What was the market rate when this deal was executed?"
- "What future EUR obligations are not yet covered?"

### 2. Get A Structured Answer

Each answer should combine:

- a short narrative summary
- a compact table of evidence
- clear filters used
- confidence or data-quality notes where relevant

### 3. Drill Into A Deal

From any deal row, the user can open a deal explainer view that shows:

- client
- bank
- currency
- execution date
- pricing fields from the deal
- related event/log rows
- related leg/exposure totals
- benchmark market context for the same date
- notable data-quality warnings

### 4. View Net Exposure

If future obligations are uploaded, the user can see:

- obligations by currency and date bucket
- existing deal/hedge coverage
- approximate net uncovered exposure
- concentration and timing risks

## Key Capabilities

### Capability 1: Client Exposure Summary

The agent summarizes a client's exposure footprint based on available internal data.

Outputs:

- recent deal count
- total notional proxy
- top currencies
- top banks
- recent activity trend
- flagged concentration risks

### Capability 2: Deal Explainer

The agent explains one deal using a curated join path rather than raw table dumps.

Inputs likely include:

- `prico.iskaot`
- `prico.bankim`
- `prico.matbeot`
- aggregated `prico.nigrarot_bankaiyot`
- aggregated `prico.paku`
- aggregated `prico.ssars`
- aggregated `prico.yoman`

Outputs:

- business summary of the deal
- timeline/evidence summary
- pricing fields and operational context
- missing or suspicious data notes

### Capability 3: Market Context

The agent compares deal pricing to historical market context on the deal date.

Possible benchmark sources to validate:

- `dbo.CurrencyPairsHistory`
- `dbo.shar_yomi`

Outputs:

- deal date benchmark rate
- delta between internal deal rate and benchmark
- explanation of whether the difference looks small, normal, or unusual
- warning when the currency mapping is ambiguous

### Capability 4: Concentration Analysis

The agent identifies concentrations in:

- bank usage
- currency usage
- recent deal activity
- near-term exposures

Outputs:

- ranked concentration tables
- concentration commentary
- optional simple charts in the UI layer

### Capability 5: Netting View

The agent accepts a user-uploaded Excel or CSV file of future obligations and compares it against known existing deals.

Outputs:

- obligations grouped by currency and date bucket
- matched hedge/deal coverage
- net uncovered amount
- notes about assumptions and incomplete mappings

## Semantic Layer Requirements

The copilot must not query raw tables arbitrarily. It should rely on approved semantic paths derived from the current analysis artifacts.

Initial canonical entities:

- client
- deal
- bank
- currency
- deal leg / exposure
- execution log
- post-deal event
- future obligation

Initial approved join patterns:

- `prico.iskaot.lakoah_mispar -> prico.lekohot.mispar_lakoah`
- `prico.iskaot.mispar_bank -> prico.bankim.mispar_bank`
- `prico.nigrarot_bankaiyot.ishur_iska -> prico.iskaot.ishur_iska`
- `prico.yoman.FXNumber -> prico.iskaot.ishur_iska`
- `prico.paku.iska -> prico.iskaot.ishur_iska`
- `prico.ssars.iska -> prico.iskaot.ishur_iska`

One-to-many sources should be aggregated before joining to the base deal table.

## Functional Requirements

### Querying

- The system must accept plain-language questions.
- The system must map questions into a constrained set of supported intents.
- The system must always apply client-level access constraints.
- The system must return both narrative and structured evidence.

### Deal Explanation

- The system must support lookup by deal ID.
- The system must explain which source tables contributed to the answer.
- The system must indicate when expected related data was missing.

### Market Context

- The system must support benchmark lookup by deal date and currency mapping.
- The system must show when benchmark confidence is low.

### File Upload

- The system must accept Excel or CSV uploads for future obligations.
- The system must normalize columns into date, currency, amount, and optional supplier/business label.
- The system must surface unmatched or low-confidence rows.

### Security

- The system must run in a read-only manner.
- The system must support on-prem deployment assumptions.
- The system must mask or restrict sensitive identifiers where needed.
- The system must never expose cross-client data without explicit authorization.

## Non-Functional Requirements

- response time for common queries should feel interactive
- output must be auditable
- all calculations should be traceable to source rows
- errors should fail safely with explanation
- architecture should support on-prem deployment

## Suggested UI Flow

### Home View

- client selector
- question input
- recent suggested prompts
- latest exposures snapshot

### Answer View

- narrative answer
- evidence table
- filters and assumptions
- follow-up suggested questions

### Deal Drawer / Detail View

- deal summary
- timeline/evidence blocks
- market context panel
- anomalies / warnings panel

### Exposure View

- bank concentration
- currency concentration
- obligation vs hedge coverage
- net uncovered buckets

## Example Questions

- "Summarize this client's activity in the last 30 days."
- "Which currencies are most active for this client?"
- "Which banks handled most of the client's recent deals?"
- "Explain deal 200462."
- "Was the rate on deal 200462 close to market on that day?"
- "What upcoming EUR obligations are still uncovered?"
- "Show me all deals above a given rate threshold."

## Example Output Shape

### Narrative

"Client 9192 had 14 recent deals, mostly concentrated in EUR and USD activity through Bank 26. The largest recent cluster occurred on February 2, 2026. One reviewed deal appears materially different from recent pricing norms, but benchmark-rate mapping should be confirmed."

### Structured Blocks

- summary metrics
- recent deals table
- concentration table by bank
- concentration table by currency
- deal explanation panel
- benchmark comparison panel
- data-quality notes

## Architecture Outline

### Data Sources

- internal SQL Server database
- optional uploaded Excel/CSV obligations
- optional historical FX benchmark table

### Application Layers

- semantic query layer over approved joins
- intent parser for supported question classes
- answer composer for narrative plus evidence
- UI/dashboard layer

### Recommended Implementation Style

- read-only API
- deterministic SQL templates for supported intents
- LLM used for intent understanding and answer narration
- no unrestricted autonomous SQL generation in the first POC

## Success Criteria

The POC is successful if:

- a user can ask plain-language questions and get correct client-scoped answers
- deal explanations are trusted by Prico users
- concentration summaries are meaningful and easy to act on
- uploaded obligations can be turned into an understandable net exposure view
- the demo clearly shows how Prico's expertise becomes software

## Demo Script Recommendation

1. Select a client.
2. Ask for a recent activity summary.
3. Show bank and currency concentration.
4. Open a specific deal and explain it.
5. Show market context for the deal date.
6. Upload future obligations.
7. Show net uncovered exposure by currency/date bucket.

## Risks And Open Questions

- exact business meaning of some pricing fields still needs validation
- benchmark FX source of truth must be confirmed
- obligation upload normalization may require client-specific mapping logic
- some date fields and legacy values may contain placeholders or inconsistent formats
- sparse related records may create partial explanations for some deals

## Recommended MVP Boundary

Phase 1 should support:

- one client at a time
- one primary deal product family
- a limited set of question types
- curated deal explainer
- simple benchmark lookup
- simple concentration summaries
- optional basic obligations upload

This keeps the POC focused, credible, and visually impressive without depending on full semantic coverage of the entire database.
