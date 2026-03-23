# Backend Deployment Note

Last Updated: 2026-03-23

This file is now a legacy pointer.

Current canonical deployment guidance for the core platform lives in:

- [`docs/references/railway_launch_runbook.md`](/Users/danielbenassaya/Code/personal/talmudpedia/docs/references/railway_launch_runbook.md)

Important status:

- the old Heroku deployment flow in this file is no longer the canonical deployment path
- the current first-production deployment target is Railway for compute plus Cloudflare R2 for bundle storage
- Sprite and Cloudflare Workers remain external runtime dependencies

If Heroku deployment needs to be revived later, write a separate legacy-specific runbook instead of restoring competing canonical instructions here.
