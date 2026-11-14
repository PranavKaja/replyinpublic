# ReplyInPublic

ReplyInPublic collects public comments across 5 platforms (YouTube, Instagram, TikTok, X, and Reddit) for kitchen brands, records whether the brand already replied, and ranks brands equally across all sources by unanswered comments from the last 14 days.

Built at HackUMass XIV with Cursor, Grok, Gemini, and Claude.

## Setup

Python 3.12. From this folder:

```
uv python install 3.12
uv venv --python 3.12 .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set:

- `DATABASE_URL`: Tiger Data (Postgres with TimescaleDB) connection string
- `YOUTUBE_API_KEY`: YouTube Data API v3 key
- `GEMINI_API_KEY`: Google AI Studio Gemini API key (active on Tier 1 Pay-as-you-go; uses `gemini-3.5-flash` and `gemini-3.5-flash-lite`)
- `APIFY_TOKEN`: Apify token for Instagram, TikTok, X, and Reddit scrapers
- `ENSEMBLEDATA_API_KEY`: EnsembleData token for scheduled TikTok pulls (50 units per day)
- `COPILOT_TOKEN`: optional on localhost; required on production so `/api/copilot` is not public

`.env` is gitignored. Do not commit it.

Production on Vultr: see [deploy/VULTR.md](deploy/VULTR.md). Systemd timers run YouTube every 30 minutes, Instagram/X/Reddit hourly, EnsembleData TikTok twice daily (Eastern), and labeling every 2 hours.

```
.venv\Scripts\python -m app.schema
.venv\Scripts\python -m app.worker
.venv\Scripts\python -m app.segment
.venv\Scripts\python -m app.collect_social
.venv\Scripts\python -m uvicorn app.main:app --port 8765
```

The worker runs once and exits. Run it again when you want a refresh. A video fetched less than 30 minutes ago is skipped. Each brand is searched at most twice per Eastern day. The first two runs of a day each spend one discovery pass. Later runs only refresh comments on the stored video ids.

## What one pass does

For each brand in `brands.json`:

1. Read the latest 5 uploads on the brand channel (`playlistItems`, 1 unit).
2. If that brand has had fewer than 2 discovery passes today, search each `search_terms` entry for videos from the last 30 days (`search.list`, 100 units per term). Drop the brand's own channel. Keep a video only when the title or description contains a search term. Store the 4 with the most comments.
3. Read up to 2 pages of newest comments on each stored active video that is due (`commentThreads.list`, 1 unit per page).
4. `commentThreads` returns at most 5 replies. When `totalReplyCount` is above 5, the worker calls `comments.list` with `parentId` and keeps paging until it finds the brand channel or the replies end. `brand_replied` is true only when a reply's `authorChannelId` is that brand's `youtube_channel_id`. `posted_at` is the comment's original `publishedAt` and is not changed on later upserts.

Rows with no URL, no text, or no publish time are counted in `runs.rejected` and are not inserted. The brand's own comments, and the video owner's comments on someone else's video, are not stored. Quota units for the pass are stored in `runs.units`.

The daily YouTube quota is 10,000 units. A full discovery pass is about 2,500 units before comment pages. Two passes in one day use about 5,000, which leaves the rest for comment refresh.

## Schema

`mentions` is a hypertable on `posted_at`. Timescale requires that column in every primary key and unique key, so the primary key is `(id, posted_at)` and the unique key is `(platform, native_id, posted_at)`. The worker upserts on that unique key.

`python -m app.schema` tries to add a foreign key from `labels (mention_id, posted_at)` to `mentions`. If Timescale rejects it, `mention_id` stays indexed and the rest of the schema still applies.

`brand_rank` ranks every brand by comments with `brand_replied` false in the last 14 days. Unknown reply status (a scan that hit the reply page cap) is not counted as unanswered.

```
SELECT * FROM brand_rank;
```

To move off Tiger later: dump, restore, and change `DATABASE_URL`. The hypertable becomes a normal table. The credits last about 30 days, so decide by mid-December.
