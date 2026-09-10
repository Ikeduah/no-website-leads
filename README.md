# No-Website Lead Finder

Finds service businesses in MA, CT and NY that have a Google Business Profile
but no real website. Outputs a CSV you can pitch from, and optionally a rich
JSON with enough per-lead data for an agent to build a mock site.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Then add your API key. Copy the template and paste your key into it:

    cp .env.example .env
    # open .env and replace your_key_here with your real key

The script reads `.env` automatically on startup, and `.env` is gitignored so
your key never gets committed. An exported `GOOGLE_PLACES_API_KEY` still works
too and takes precedence over `.env`.

## Verify your key first

    python no_website_leads.py --test

One API call. Confirms the key, billing and field mask are working before
you spend anything on a real sweep.

## Real runs

    python no_website_leads.py --target 50
    python no_website_leads.py --state CT --target 100
    python no_website_leads.py --target 0 --max-calls 800

`--max-calls` is a per-run ceiling so a bad loop can't run up your bill.

## Staying inside the free tier

You get ~1,000 free requests per month per SKU. To guarantee you never cross
that — even across many separate runs — the script keeps a running monthly
tally in `.api_usage.json` (gitignored) and refuses the request that would go
over:

    python no_website_leads.py --state CT        # stops when the month's free 1,000 is spent

`--monthly-limit` defaults to `1000` and is enforced across every run in the
calendar month, not just the current one. A run ends at whichever comes first:
its own `--max-calls`, or the month's remaining free budget. When the month's
budget is gone it exits without spending:

    Monthly free-tier limit reached: 1000/1000 base-tier requests used in 2026-09.

The base sweep and `--profiles` are separate SKUs with separate free
allowances, so they're counted separately — using up one doesn't block the
other. To deliberately spend past the free tier, raise the limit, e.g.
`--monthly-limit 2000`.

Two caveats: the month boundary is UTC, and the tally only counts *this
script's* calls — if the same API key is used elsewhere on the project, check
the real number in Cloud Console. For a safety margin, set `--monthly-limit`
a little below 1,000 (say `950`).

## Resume between runs — `--resume`

    python no_website_leads.py --resume

Records which queries it has fully swept (in `.seen_places.json`, gitignored)
and skips them next time, so a re-run spends its budget only on new ground. It
also remembers the businesses you already captured and won't add them twice;
new leads are **appended** to the CSV, so your growing pipeline (and any
outreach columns you add by hand) is never overwritten.

This is the natural partner to `--monthly-limit`: point the tool at a big area,
and each month it advances further into the sweep instead of re-running the
same first slice. Over a few months you cover everything without ever paying —
and without re-checking a business you've already seen.

    python no_website_leads.py --resume --reset-cache   # forget progress, start over

Per Google's terms the cache stores only place IDs (cacheable indefinitely) and
phone numbers, for dedupe — never the rich fields.

Note: appended CSV rows are sorted within each run, not across the whole file;
open it in a spreadsheet to sort the full list. `lead_profiles.json` is always
the current batch only (it holds cache-restricted data), not an accumulating
file.

## What counts as a lead — the `presence` column

A business is kept if it has a phone, is operational, clears `--min-reviews`,
and has no *real* website. The CSV's `presence` column says what web presence
it does have, warmest (coldest web presence) first:

- `none` — no link at all. Zero online home. The warmest pitch.
- `social` — the only link is a Facebook / Instagram / Linktree / Yelp page.
  These used to be dropped (Google lists the social URL as the "website"), but
  they're prime prospects — "your Facebook page isn't a website."
- `builder` — a Google auto-generated stub (`business.site`, `sites.google.com`).
  Technically a page, but barebones; an easy upgrade pitch.

`existing_link` holds that social/builder URL when there is one, so you can see
what they're currently sending people to.

## The CSV as a pipeline

The last four columns turn the CSV into a lightweight CRM:

- `first_seen` — auto-filled with the date the lead was discovered, so you can
  see how long one has been sitting.
- `contacted_date`, `outcome`, `notes` — blank for you to fill in as you work
  the lead (e.g. outcome: `left voicemail`, `booked call`, `not interested`).

With `--resume` these stay put: new leads are appended and existing rows are
never rewritten, so whatever you type here survives every later run. (A plain
run without `--resume` overwrites the file, so do your tracking on resumed
runs, or keep the working copy in a spreadsheet.)

## Building mock sites — `--profiles`

    python no_website_leads.py --state CT --target 40 --profiles

Adds `lead_profiles.json` next to the CSV: one rich record per lead with name,
category, services, hours, address, location (lat/lng), an editorial
description, and real Google reviews (great as testimonials) — enough for an
agent to mock up a site and pitch it. Hand that file to your site-building
agent.

Note on caching: per Google's terms the script stores place IDs and phone
numbers for dedupe, but the other fields should be re-fetched rather than kept
long-term — treat `lead_profiles.json` as a working file for the current batch,
not a permanent database.

## Cost

The base field mask asks for website, phone and rating, which puts Text Search
in Google's Enterprise tier: about 1,000 free requests per month, then roughly
$35 per 1,000. Each request returns up to 20 businesses, so the free tier
covers about 20,000 businesses a month.

`--profiles` adds reviews, description and price level, which move the request
to the **Enterprise + Atmosphere** tier — a bit more per 1,000 (~$40). Only
turn it on for batches you actually intend to build sites for.

Set a budget alert anyway: Google Cloud Console -> Billing -> Budgets & alerts.

## Tuning

Edit `BUSINESS_TYPES` and `CITIES` at the top of the script. `MIN_REVIEWS`
(default 3) filters out dead listings; override it per run with
`--min-reviews`. Lower it to catch legitimate small-city businesses that only
have one or two reviews:

    python no_website_leads.py --state CT --min-reviews 1
