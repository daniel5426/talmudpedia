# UI Blocks Tool Reference

Last Updated: 2026-03-29

This is the canonical reference for the built-in `UI Blocks` tool and its frontend integration contract.

## Purpose

`UI Blocks` is a platform built-in tool that validates and normalizes a strict JSON analytical UI bundle.

The backend does not render HTML. It only returns the canonical output envelope:

- `kind: "ui_blocks_bundle"`
- `contract_version: "v1"`
- `bundle: { title?, subtitle?, rows: [...] }`

## V1 Block Set

V1 supports a fixed starter set:

- `kpi`
- `pie`
- `bar`
- `compare`
- `table`
- `note`

## Input Contract

The built-in tool input is strict JSON:

- `title?`
- `subtitle?`
- `rows`
- `rows[].blocks`

Validation rules:

- `rows` is required and non-empty
- `rows[].blocks` is required and non-empty
- block ids must be unique across the bundle
- each row total span must be at most `12`
- block-specific required fields must be present

## Output Contract

Successful tool execution returns:

```json
{
  "kind": "ui_blocks_bundle",
  "contract_version": "v1",
  "bundle": {
    "title": "optional",
    "subtitle": "optional",
    "rows": [
      {
        "blocks": [
          {
            "kind": "kpi",
            "id": "deals",
            "span": 3,
            "title": "Deals",
            "value": "24"
          }
        ]
      }
    ]
  }
}
```

## Frontend Requirement

`UI Blocks` is frontend-dependent.

Platform metadata now exposes:

- `required: true`
- `renderer_kind: "ui_blocks"`
- `package_name: "@agents24/ui-blocks-react"`
- `contract_package_name: "@agents24/ui-blocks-contract"`
- `install_command: "npx @agents24/ui-blocks-react init"`
- hosted template support for `classic-chat`
- install docs URL for custom frontends

## Hosted Support

Hosted v1 support is built into the `classic-chat` template.

The template:

- shows a loading skeleton when a tool event declares `renderer_kind="ui_blocks"`
- renders the completed bundle when `output.kind === "ui_blocks_bundle"`
- does not rely on PRICO-specific tool slugs

## OSS Source Of Truth

The canonical OSS source for this contract lives in the sibling repo:

- `/Users/danielbenassaya/Code/personal/agents24-ui-blocks`

Published npm packages:

- `@agents24/ui-blocks-contract`
- `@agents24/ui-blocks-react`

Custom frontend install now follows a shadcn-style flow:

- install `@agents24/ui-blocks-contract`
- install `@agents24/ui-blocks-react`
- run `npx @agents24/ui-blocks-react init`
- import the local generated source from `src/components/ui-blocks`
