Last Updated: 2026-03-22

# PRICO Widget Output Tool Vision Summary

## Core conclusion

The right direction is to avoid binding a fixed UI to each PRICO domain tool. Instead, keep:

1. Domain data tools
2. Agent reasoning
3. A separate UI widget output tool

This preserves a clean split between data retrieval, interpretation, and presentation.

## Why this direction is better

- The same domain tool can support very different user intents.
- Some PRICO outputs are highly visual, while others are mostly explanatory.
- A fixed UI per tool would force charts/tables even when plain text is better.
- A widget output tool lets the agent show visuals only when they materially help.

## Recommended rendering model

Use one widget-tool call per assistant answer in the normal case.

That single call should contain:

- screen metadata
- multiple rows
- multiple widgets per row
- widget width/span hints

This gives the agent control over composition while keeping rendering centralized.

## Recommended layout contract

The conversation converged on:

- one response bundle
- sections or rows
- widgets inside rows
- `span` on each widget using a 12-column mental model

Examples:

- `span=12` full width
- `span=6` half width
- `span=3` quarter width

This is the right abstraction level. The agent controls semantic grouping; the renderer controls actual layout, spacing, and mobile fallback.

## Recommended widget set for v1

- KPI cards
- pie chart
- bar chart
- comparison chart
- table
- note / text panel

This is enough for:

- bank concentration
- currency concentration
- recent activity summary
- compare-to-market
- ranked lists / top deals

## Good policy for when widgets should appear

Use widgets when the answer is mainly about:

- distribution
- ranking
- comparison
- trend
- summary metrics

Avoid or de-emphasize widgets when the answer is mainly about:

- explanation
- caveats
- qualitative interpretation
- business meaning of a specific deal

## Contract format recommendation

Using a compact DSL instead of JSON is a good idea for this use case.

Why:

- lower token cost
- easier for the model to emit consistently
- easier to read in logs/debugging
- expressive enough for rows, spans, charts, and tables

The proposed line-based DSL is directionally good:

- `screen`
- `row`
- widget commands like `kpi`, `pie`, `bar`, `table`, `note`
- short attributes like `s`, `t`, `v`, `x`
- block payloads ending with `end`

## Recommended improvements

### 1. Keep the DSL semantic, not visual-CSS-like

The agent should choose:

- what widgets to show
- which widgets belong together
- rough width/span

The agent should not choose:

- pixel widths
- exact grid classes
- responsive breakpoints
- styling details

### 2. Add a strict validation layer

The renderer/parser should enforce:

- supported widget types only
- unique widget ids
- valid spans
- row total span <= 12
- valid chart/table payload shape

If invalid, fallback to stacked rendering instead of breaking the UI.

### 3. Add a stable widget taxonomy early

Do not let the model invent widget types. Freeze a small set and version it.

Suggested v1 types:

- `kpi`
- `pie`
- `bar`
- `compare`
- `table`
- `note`

### 4. Keep narrative outside or adjacent to widgets

Do not force all explanation into widget payloads. The best UX is usually:

- optional visual bundle
- concise natural-language answer

That keeps the agent conversational instead of dashboard-like.

### 5. Prefer one render bundle per turn

Multiple widget-tool calls should be the exception, mainly for iterative refinement or staged loading. Default should stay:

- one assistant answer
- one widget render bundle

### 6. Consider provenance / confidence fields

For financial/business analysis, add optional support for:

- data source label
- time window
- confidence / completeness note
- caveat / footnote

This will matter once users ask why a chart looks incomplete or skewed.

## Recommended product vision

PRICO should behave as a conversational analytical copilot, not as a dashboard disguised as chat.

That means:

- text is the default output mode
- widgets are optional evidence/presentation blocks
- visuals appear only when they improve understanding
- the same domain tool can support both plain answers and richer analytical views

This is the right product shape for the standalone app too, because it keeps the app flexible, agentic, and easier to evolve.

## Short recommendation

Build:

- narrow domain tools
- one structured widget output tool
- one compact DSL contract
- strong renderer-side validation

Do not build:

- rigid per-tool UIs
- always-on charts
- overly flexible free-form widget schemas
