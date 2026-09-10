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

`--max-calls` is a hard ceiling so a bad loop can't run up your bill.

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
