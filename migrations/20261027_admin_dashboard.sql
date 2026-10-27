-- Admin dashboard: qualify traffic and remember IP checks.
-- Run this on the sababreeze database before deploying the new API.
--
-- Orders already in the table were accepted by checkout, which rejects
-- connections outside the UAE and VPN / proxy / Tor / datacenter traffic.
-- Those orders are marked qualified. The test bypass number is left out.
-- Visits saved before this file ran were not classified, so they stay out
-- of the dashboard. New visits use the same ipapi.is check as checkout.

BEGIN;

ALTER TABLE analytics_events
  ADD COLUMN IF NOT EXISTS client_ip text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS geo_qualified boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS geo_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS country_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS visitor_id text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS channel text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS utm_source text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS utm_medium text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS utm_campaign text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS utm_content text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS landing_path text NOT NULL DEFAULT '';

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS geo_qualified boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS geo_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS country_code text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS channel text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS ip_verdicts (
  ip text PRIMARY KEY,
  allowed boolean NOT NULL,
  code text NOT NULL,
  country_code text NOT NULL DEFAULT '',
  checked_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_analytics_qualified_created
  ON analytics_events (created_at)
  WHERE geo_qualified;

CREATE INDEX IF NOT EXISTS ix_analytics_qualified_name_created
  ON analytics_events (event_name, created_at)
  WHERE geo_qualified;

CREATE INDEX IF NOT EXISTS ix_orders_qualified_created
  ON orders (created_at)
  WHERE geo_qualified;

-- Only fill rows the new API has not classified yet. Safe to run again.
UPDATE orders
SET
  geo_qualified = phone_e164 IS DISTINCT FROM '+971500000099',
  geo_code = CASE
    WHEN phone_e164 = '+971500000099' THEN 'bypass'
    ELSE 'ok'
  END,
  country_code = CASE
    WHEN phone_e164 = '+971500000099' THEN ''
    ELSE 'AE'
  END,
  channel = CASE
    WHEN coalesce(attribution->>'fbclid', '') <> '' OR coalesce(attribution->>'fbc', '') <> '' THEN 'meta'
    WHEN coalesce(attribution->>'ttclid', '') <> '' OR coalesce(attribution->>'ttp', '') <> '' THEN 'tiktok'
    WHEN coalesce(attribution->>'sc_click_id', '') <> '' OR coalesce(attribution->>'sc_cookie', '') <> '' THEN 'snap'
    WHEN position('gclid=' in coalesce(landing_url, '')) > 0 THEN 'google'
    WHEN lower(coalesce(attribution->>'utm_source', '')) IN ('meta', 'facebook', 'fb', 'instagram', 'ig') THEN 'meta'
    WHEN lower(coalesce(attribution->>'utm_source', '')) IN ('tiktok', 'tt') THEN 'tiktok'
    WHEN lower(coalesce(attribution->>'utm_source', '')) IN ('snap', 'snapchat') THEN 'snap'
    WHEN lower(coalesce(attribution->>'utm_source', '')) IN ('google', 'gads', 'youtube') THEN 'google'
    WHEN coalesce(attribution->>'utm_source', '') <> '' THEN lower(left(attribution->>'utm_source', 40))
    ELSE 'direct'
  END
WHERE geo_code = '';

COMMIT;
