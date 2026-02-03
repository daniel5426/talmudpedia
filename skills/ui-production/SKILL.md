---
name: ui-production
description: Production-grade UI page and component development for Next.js + Tailwind with shadcn/ui. Use when asked to design, polish, or build frontend pages/components, improve visual hierarchy/typography/layout, refactor UI for responsiveness/accessibility, or upgrade existing UI to a higher-quality visual standard.
---

# UI Production

## Overview
Build and polish production-grade UI in Next.js + Tailwind without generic, cookie-cutter layouts. Prioritize strong visual hierarchy, deliberate typography, and clean component architecture.

## Workflow
1. Establish constraints.
- Scan the repo for existing design system, Tailwind config, components, and typography.
- Ask only for missing essentials (brand tone, target device, content length, or must-keep elements).
- Reuse existing tokens and components unless explicitly asked to redesign.

2. Plan structure and hierarchy.
- Define the page sections and content priority before styling.
- Choose a grid and layout rhythm (section spacing, column structure).
- Identify the primary and secondary actions and make the hierarchy obvious.

3. Set typography and spacing.
- Choose a purposeful type scale and line-length targets.
- Use a consistent spacing scale; avoid ad-hoc spacing values.
- If a new font is needed, prefer `next/font` and confirm it is acceptable to add.

4. Design components and states.
- List the components needed and their states (hover, focus, active, empty, loading).
- Use semantic HTML and accessible controls.
- Keep components cohesive and reusable.

5. Implement with Next.js + Tailwind + shadcn/ui.
- Use utility classes with clear grouping and responsive variants.
- Extract repeated class groups to components or `clsx` patterns when needed.
- Avoid visual noise: favor fewer, stronger styles over many weak ones.

6. Quality gates.
- Run the checklist in `references/quality-gates.md`.
- Provide a brief QA summary and call out any intentional tradeoffs.

## Output Expectations
- Deliver concrete file edits and a short, high-signal summary.
- Explain the hierarchy, typography, and layout choices in 3-6 bullets.
- If something is ambiguous, propose 2-3 options and ask for a choice.

## References
- Read `references/ui-principles.md` for hierarchy, layout, and typography heuristics.
- Read `references/nextjs-tailwind.md` for implementation patterns.
- Read `references/quality-gates.md` for the final checklist.
