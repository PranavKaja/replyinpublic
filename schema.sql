-- ReplyInPublic schema.
-- Portable Postgres: plain SQL, one hypertable, pgvector when the server has it.
-- To move to Supabase or any Postgres, dump, restore, and change DATABASE_URL.
-- The hypertable becomes a normal table.
-- Timescale requires posted_at in every primary key and unique key on mentions.

CREATE TABLE IF NOT EXISTS brands (
  id text PRIMARY KEY,
  name text NOT NULL,
  youtube_channel_id text NOT NULL,
  instagram_handle text,
  own_handles text[] NOT NULL DEFAULT '{}',
  search_terms text[] NOT NULL DEFAULT '{}',
  support_contact text,
  reply_sla_hours integer NOT NULL DEFAULT 48
);

-- Video ids found by search or by the brand's own uploads playlist.
-- Comment refresh reads this table. Search does not run on the 30 minute loop.
CREATE TABLE IF NOT EXISTS videos (
  brand_id text NOT NULL REFERENCES brands (id),
  video_id text NOT NULL,
  channel_id text,
  surface text NOT NULL,
  title text,
  comment_count integer,
  active boolean NOT NULL DEFAULT true,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  last_comment_fetch_at timestamptz,
  PRIMARY KEY (brand_id, video_id)
);

CREATE INDEX IF NOT EXISTS videos_due_idx
  ON videos (brand_id, active, last_comment_fetch_at);

-- One Eastern-day row per brand. passes stops at 2.
CREATE TABLE IF NOT EXISTS discovery_passes (
  brand_id text NOT NULL REFERENCES brands (id),
  day date NOT NULL,
  passes integer NOT NULL DEFAULT 0,
  last_at timestamptz,
  PRIMARY KEY (brand_id, day)
);

CREATE TABLE IF NOT EXISTS mentions (
  id bigint GENERATED ALWAYS AS IDENTITY,
  posted_at timestamptz NOT NULL,
  brand_id text NOT NULL REFERENCES brands (id),
  platform text NOT NULL,
  surface text NOT NULL,
  native_id text NOT NULL,
  url text NOT NULL,
  author text,
  text text NOT NULL,
  parent_url text,
  brand_replied boolean,
  reply_text text,
  brand_reply_at timestamptz,
  brand_reply_author text,
  case_id text,
  proof text,
  collected_by text,
  collected_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id, posted_at),
  UNIQUE (platform, native_id, posted_at)
);

SELECT create_hypertable('mentions', 'posted_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS mentions_brand_posted_idx
  ON mentions (brand_id, posted_at DESC);

CREATE INDEX IF NOT EXISTS mentions_unanswered_idx
  ON mentions (brand_id, posted_at DESC)
  WHERE brand_replied IS FALSE;

CREATE INDEX IF NOT EXISTS mentions_case_id_idx
  ON mentions (case_id)
  WHERE case_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS reply_drafts (
  mention_id bigint NOT NULL,
  posted_at timestamptz NOT NULL,
  draft_text text NOT NULL,
  final_text text,
  status text NOT NULL DEFAULT 'suggested',
  source_passages jsonb,
  model text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mention_id, posted_at)
);

-- posted_at is here so a foreign key to the hypertable can include the partition column.
-- If that foreign key is rejected, mention_id stays a plain indexed column.
CREATE TABLE IF NOT EXISTS labels (
  mention_id bigint NOT NULL,
  posted_at timestamptz NOT NULL,
  type text,
  sentiment text,
  urgency text,
  is_buyer boolean,
  relevant boolean,
  model text,
  labeled_at timestamptz
);

CREATE INDEX IF NOT EXISTS labels_mention_id_idx ON labels (mention_id);

CREATE TABLE IF NOT EXISTS runs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  added integer NOT NULL DEFAULT 0,
  rejected integer NOT NULL DEFAULT 0,
  units integer NOT NULL DEFAULT 0,
  error text
);

CREATE OR REPLACE VIEW brand_rank AS
SELECT
  b.id AS brand_id,
  b.name,
  count(m.native_id)::integer AS unanswered_14d
FROM brands b
LEFT JOIN mentions m
  ON m.brand_id = b.id
 AND m.brand_replied IS FALSE
 AND m.posted_at >= now() - interval '14 days'
GROUP BY b.id, b.name
ORDER BY unanswered_14d DESC, b.name;
