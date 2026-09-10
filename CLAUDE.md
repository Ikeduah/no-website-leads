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
`places.websiteUri`, which is how we judge web presence.

A result is kept as a lead only if all of these hold (see `is_lead`):
- it has no *real* website — `classify_presence(websiteUri)` is not `"website"`
- `businessStatus` is `OPERATIONAL`
- a `nationalPhoneNumber` exists (no phone means no way to pitch)
- `userRatingCount` >= min reviews (default 3, overridable via `--min-reviews`)

`classify_presence` buckets each listing by domain into `none` (no link),
`social` (Facebook/IG/Linktree/Yelp/etc), `builder` (Google's auto stubs like
`business.site`) or `website` (a real site — the only one that's *not* a lead).
This matters: Google often lists a business's Facebook page as its "website",
so social-only shops used to be wrongly rejected. They're now kept and tagged
via the CSV `presence` column, sorted warmest-first (`none` before `social`
before `builder`).

Leads are deduped by phone number across queries. It sweeps
`BUSINESS_TYPES` x `CITIES`, two pages per query, 20 results per page.

## Rich profiles (`--profiles`)

`--profiles` swaps in `PROFILE_FIELD_MASK` (base fields + reviews, hours,
editorial description, services/types, location, price level, photos) and
writes `lead_profiles.json` alongside the CSV — one structured record per lead
(`to_profile`) with everything an agent needs to mock up a website: name,
category, services, hours, address, lat/lng, description, and real reviews as
testimonials. Those extra fields are Atmosphere-tier, so this costs more (see
below) — it's opt-in for that reason.

## Running it

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env                     # then paste your key into .env
    python no_website_leads.py --test        # 1 call, verifies setup
    python no_website_leads.py --target 50   # small real run

The key is read from `.env` via a tiny inline loader (`load_dotenv`) — no
python-dotenv dependency, to keep the stdlib-plus-requests rule. An exported
`GOOGLE_PLACES_API_KEY` overrides `.env`.

    python no_website_leads.py --profiles    # + lead_profiles.json for mock sites

Flags: `--test`, `--target`, `--state {MA,CT,NY}`, `--max-pages`,
`--max-calls`, `--min-reviews`, `--profiles`, `--monthly-limit`.

## Cost constraint — important

Requesting website + phone + rating puts Text Search in Google's **Enterprise**
field tier. Roughly 1,000 free requests per month, then about $35 per 1,000.
Each request returns up to 20 businesses, so the free tier covers around
20,000 businesses monthly.

`--profiles` adds reviews / editorialSummary / priceLevel, which push the
request into the pricier **Enterprise + Atmosphere** tier (~$40/1,000). That's
why it's a flag, not the default — keep plain lead-finding runs on the base
mask.

Google retired the old universal $200 monthly credit in March 2025. Free
allowances are now per-SKU and do not pool. There is no automatic spend cap.

**Do not remove or bypass `--max-calls` or `--monthly-limit`.** They are the
guards against a real bill. When adding features, keep every API call routed
through the single `search()` function so both counters stay accurate.

## Staying inside the free tier (`--monthly-limit`)

`--max-calls` only bounds one run; it can't stop three runs in a month from
together crossing the free 1,000. So the script also keeps a persistent
monthly tally in `.api_usage.json` (gitignored) and never makes the request
that would exceed `--monthly-limit` (default `MONTHLY_FREE_LIMIT` = 1000).

- `search()` returns `(places, token, billed)`; the counter (`record_call`)
  only advances on a 200 response — the case Google charges for. Failed calls
  don't count.
- Counts are keyed by `YYYY-MM` (UTC) **and** SKU: `base` for normal runs,
  `atmosphere` for `--profiles`. The two SKUs have separate free allowances and
  are tracked separately, so exhausting one doesn't block the other.
- A run stops at `min(--max-calls, month's remaining budget)`. `save_usage`
  writes atomically (temp + rename) so an interrupt can't lose the count.
- The tally only sees this script's calls; if the key is shared, the real
  number lives in Cloud Console.

## Next tasks (in priority order)

1. **Resume between runs.** Right now a re-run starts from scratch and burns
   calls re-checking the same businesses. Cache seen place IDs to a local
   JSON or SQLite file and skip them. Note Google's terms: place IDs may be
   stored indefinitely, but most other returned fields may not be cached
   long-term — store IDs and phone numbers for dedupe, re-fetch the rest.
   (`places.id` is already in the field mask, so it's on hand to cache.)

2. **Outreach status tracking.** Add columns for contacted date, outcome and
   notes so the CSV doubles as a simple pipeline.

## Done

- **`--min-reviews` flag.** `MIN_REVIEWS` is still the default (3) but is now
  overridable per run; `is_lead(place, min_reviews)` takes the threshold as an
  argument.
- **`.env` support.** `load_dotenv()` reads the key from `.env` on startup.
- **`presence` column / social-only leads.** `classify_presence` tags each
  lead `none` / `social` / `builder`; social-only shops (Facebook page as the
  "website") are now kept instead of dropped, and the CSV sorts warmest-first.
- **`--profiles`.** Rich per-lead JSON (`lead_profiles.json`) with reviews,
  hours, description, services and location for building mock sites.
- **`--monthly-limit` / free-tier guard.** Persistent per-month, per-SKU tally
  in `.api_usage.json` that hard-stops before crossing the free 1,000.

## Style notes

Plain, readable Python. Standard library plus `requests` only — no heavy
dependencies. Short comments that explain *why*, not *what*.
