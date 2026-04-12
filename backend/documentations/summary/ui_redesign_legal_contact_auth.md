# UI Redesign: Contact, Legal, and Beta Access
Last Updated: 2026-04-12

## Scope
Redesigned the contact page, terms of service, privacy policy, and the "Private beta" mode in the authentication flow. The goal was to migrate away from heavy box-shadow layouts to a clean, minimalist, and polished aesthetic.

## Changes

1. **`components/marketing/legal-page.tsx`**
   - Transformed the legal page layout from a centered floating card to a seamless, full-bleed elegant document structure.
   - Introduced a prominent back link, clean section numbering using `font-mono`, and hover micro-interactions (`group-hover:opacity-100` on a subtle background layer inside sections).

2. **`components/marketing/contact-form.tsx`**
   - Stripped away default borders, shadows, and heavy backgrounds.
   - Redesigned inputs to use a bottom-border-only style (`border-t-0 border-l-0 border-r-0 border-b`) with `focus:border-black`.
   - Updated labels to `uppercase tracking-widest` for a high-end, editorial feel.
   - Refined error/success states to be subtle and modern.

3. **`app/(landing)/contact/page.tsx`**
   - Overhauled the grid layout. Replaced the generic visual style with a stark, modern two-column look: Left side handling the typography and context with generous padding, right side handling the form over a whisper-light `bg-gray-50/30` background.

4. **`components/marketing/beta-access-panel.tsx`**
   - Redesigned the "Private beta" access lockout mode on the `/auth/login` and `/auth/signup` pages.
   - Refactored the core layout into a compact `<ContactForm compact />` inside a clean `border-gray-100` panel, accompanied by a pulsing status indicator replacing the previous plain text approach.
   - Enhanced the button alignment and support links section for seamless integration with the authentication flows context.
