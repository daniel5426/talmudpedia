# Agents24 Public Docs Site

Last Updated: 2026-04-10

This app is the public Nextra docs site for `docs.agents24.dev`.

## Purpose

- ship public, task-first documentation separately from the product frontend
- keep public pages curated while the canonical engineering docs remain under `../docs/`
- turn documentation work into repeatable platform validation

## Commands

```bash
pnpm install
pnpm validate:content
pnpm build
pnpm dev
```

## Content Rules

- every `page.mdx` file must include the required frontmatter contract
- public docs should explain tasks and expectations, not dump internal architecture prose
- when public behavior changes, update the mapped internal source and public page together
