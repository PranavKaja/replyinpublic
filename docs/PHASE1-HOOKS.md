# Phase 1 hooks (SaaS path)

This weekend build stays Phase 1 per `12-Overheard/docs/LATER-PHASES.md`. Later phases (public scores, shopper filing, concierge, badges) are not shipped here. These hooks let them plug in without a rewrite.

| Hook | Table / field | Later use |
|---|---|---|
| Case id | `mentions.case_id` | Countdown, concierge callback codes |
| Reply proof | `mentions.proof`, `collected_by` | Solid-data scores (Phase 2) |
| First brand reply | `mentions.brand_reply_at`, `brand_reply_author` | Reply speed metrics when data is connected |
| SLA countdown | `brands.reply_sla_hours` (default 48), `support_contact` | Managed Desk, named-person rule |
| Draft workflow | `reply_drafts` (suggested, approved, edited, rejected) | Learning loop before auto-post (Phase 1.5) |

Run `python -m app.schema` after pull to migrate Tiger. Phase 2 adds public scores only when reply times come from connected accounts or hand-checked threads, not from scraped guesses alone.