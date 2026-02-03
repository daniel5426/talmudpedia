# Next.js + Tailwind Patterns

## Structure
- Prefer App Router with `app/` layouts and route segments.
- Use layout components for shared chrome and page shells.
- Keep page components slim; move sections into `components/`.

## shadcn/ui
- Prefer shadcn/ui primitives for common patterns (buttons, inputs, dialogs, tabs).
- Customize via Tailwind classes instead of rewriting components.
- Keep variants limited and consistent across the app.

## Tailwind Usage
- Group classes by: layout, spacing, typography, color, effects.
- Use responsive variants (`sm:`/`md:`/`lg:`) intentionally; avoid stacking too many breakpoints.
- Favor Tailwind tokens over arbitrary values; introduce CSS variables only when needed.

## Typography
- Use `next/font` for custom fonts when allowed.
- Define a small set of text styles and reuse them.

## Reuse
- Extract repeated class strings into components or `clsx` helpers.
- Use `cn`/`clsx` patterns when conditional styles are required.
