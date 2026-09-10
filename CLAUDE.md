# CLAUDE.md

Context for Claude Code working on this project.

## What this is

A lead-generation script for Issachar Solutions. It finds service businesses
in Massachusetts, Connecticut and New York that have a Google Business Profile
but **no website**. Those are the warmest possible prospects for a web design
pitch: they already care about being found online, but have nowhere to send
people.

Output is `no_website_leads.csv` with name, phone, address, city, state,
category, rating, review count and a Google Maps link.

## How it works

`no_website_leads.py` hits the Google Places API (New) `places:searchText`
endpoint. The key detail is the `X-Goog-FieldMask` header — it requests
`places.websiteUri`, and a business with that field absent is treated as
having no website.

A result is kept as a lead only if all of these hold (see `is_lead`):
- `websiteUri` is missing
- `businessStatus` is `OPERATIONAL`
- a `nationalPhoneNumber` exists (no phone means no way to pitch)
- `userRatingCount` >= `MIN_REVIEWS` (default 3, filters dead listings)

Leads are deduped by phone number across queries. It sweeps
`BUSINESS_TYPES` x `CITIES`, two pages per query, 20 results per page.

## Running it

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_PLACES_API_KEY="..."
    python no_website_leads.py --test        # 1 call, verifies setup
    python no_website_leads.py --target 50   # small real run

Flags: `--test`, `--target`, `--state {MA,CT,NY}`, `--max-pages`, `--max-calls`.

## Cost constraint — important

Requesting website + phone + rating puts Text Search in Google's **Enterprise**
field tier. Roughly 1,000 free requests per month, then about $35 per 1,000.
Each request returns up to 20 businesses, so the free tier covers around
20,000 businesses monthly.

Google retired the old universal $200 monthly credit in March 2025. Free
allowances are now per-SKU and do not pool. There is no automatic spend cap.

**Do not remove or bypass `--max-calls`.** It is the only guard against a bad
loop running up a real bill. When adding features, keep every API call routed
through the single `search()` function so the counter stays accurate.

## Next tasks (in priority order)

1. **`--min-reviews` flag.** `MIN_REVIEWS` is currently a module constant.
   Smaller cities like Ansonia or Elmira have legitimate businesses with 1-2
   reviews that are being filtered out. Make it a CLI arg.

2. **Flag social-only businesses.** Many "no website" listings actually point
   people to a Facebook or Instagram page. Google still reports no
   `websiteUri`, so they pass the filter, but they need a different pitch
   ("your Facebook page isn't a website") versus true zero-presence
   ("you have nothing"). Add a `presence` column with values like
   `none` / `social` and sort them separately in the CSV.

3. **Resume between runs.** Right now a re-run starts from scratch and burns
   calls re-checking the same businesses. Cache seen place IDs to a local
   JSON or SQLite file and skip them. Note Google's terms: place IDs may be
   stored indefinitely, but most other returned fields may not be cached
   long-term — store IDs and phone numbers for dedupe, re-fetch the rest.

4. **Outreach status tracking.** Add columns for contacted date, outcome and
   notes so the CSV doubles as a simple pipeline.

## Style notes

Plain, readable Python. Standard library plus `requests` only — no heavy
dependencies. Short comments that explain *why*, not *what*.
