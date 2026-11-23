# Phase 1 hooks (SaaS path)

This weekend build stays Phase 1. Later phases (public scores, shopper filing, concierge, badges) are not shipped here. These hooks let them plug in without a rewrite.

| Hook | Table / field | Later use |
|---|---|---|
| Case id | `mentions.case_id` | Countdown, concierge callback codes |
| Reply proof | `mentions.proof`, `collected_by` | Solid-data scores (Phase 2) |
| First brand reply | `mentions.brand_reply_at`, `brand_reply_author` | Reply speed metrics when data is connected |
| SLA countdown | `brands.reply_sla_hours` (default 48), `support_contact` | Managed Desk, named-person rule |
| Draft workflow | `reply_drafts` (suggested, approved, edited, rejected) | Phase 1 examples for the next draft. A tuned model is Phase 2 |
| Publish queue | `publish_queue` | Phase 1 handoff to an agent. Official posting is Phase 2 |

Run `python -m app.schema` after pull to migrate Tiger. Phase 2 adds public scores only when reply times come from connected accounts or hand-checked threads, not from scraped guesses alone.

There is no Phase 1.5 (decided 2026-11-15). The pieces below are Phase 1. Official posting, a public reply plus a DM in one approval, helpdesk sync, and brand rulebooks are Phase 2, because they need a connected account or private order data.

## Phase 1 pieces that used to be called 1.5

| Piece | Where | Phase |
|---|---|---|
| Brand console + pilot signup form | `onboarding_leads`, `/api/onboard` | 1. The console page is retired (`/console` opens the inbox), and its routes need a team sign-in |
| Connection stubs | `brand_connections` (status `pilot_pending` until OAuth) | 1 stub. Real connection is Phase 2 |
| Approve to publish queue | `publish_queue` after draft approve/edit | 1. The queue does not post |
| Demo post marker | Mark demo posted on pilot X/IG until APIs connect | 1, demo only |
| Placeholder support names | `tools/seed_support.py` | 1 |
| AI drafter and send to our bot | `POST /api/desk/agent`, team accounts only | 1. No button calls it yet. Handing a reply to our bot stays off until the bot is confirmed unable to post |