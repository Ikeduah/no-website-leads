#!/usr/bin/env python3
"""
Find service businesses in MA / CT / NY with NO real website on Google.

Usage:
    python no_website_leads.py --test           # 1 API call, verify key works
    python no_website_leads.py --target 50      # small real run
    python no_website_leads.py --state CT       # one state only
    python no_website_leads.py --profiles       # also scrape data to build mock sites
    python no_website_leads.py                  # full default run
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
from urllib.parse import urlparse

import requests

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# Fields we ask for on every run. Requesting website + phone + rating already
# puts Text Search in Google's Enterprise tier (see README). places.id is in
# the free IDs tier, so it doesn't change the price.
BASE_FIELDS = [
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "places.googleMapsUri",
]

# Extra fields for --profiles: enough for an agent to build a mock website.
# These include Atmosphere-tier fields (reviews, editorialSummary, priceLevel),
# which bump the SKU price. See the cost note in README / CLAUDE.md.
PROFILE_EXTRA = [
    "places.primaryType",
    "places.shortFormattedAddress",
    "places.location",
    "places.priceLevel",
    "places.types",
    "places.regularOpeningHours.weekdayDescriptions",
    "places.editorialSummary",
    "places.reviews",
    "places.photos",
]

BASE_FIELD_MASK = ",".join(BASE_FIELDS + ["nextPageToken"])
PROFILE_FIELD_MASK = ",".join(BASE_FIELDS + PROFILE_EXTRA + ["nextPageToken"])

# A "no website" listing whose only link is one of these isn't really online —
# it's the warmest kind of lead, but needs a different pitch than zero presence.
SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "fb.me", "instagram.com", "instagr.am",
    "linktr.ee", "linktree.com", "tiktok.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "yelp.com", "nextdoor.com", "wa.me", "t.me",
    "pinterest.com", "snapchat.com",
}
# Google's own auto-generated free stubs. Technically a page, but barebones —
# still a strong "let's build you a real site" target.
BUILDER_DOMAINS = {"business.site", "sites.google.com", "godaddysites.com"}

# How warm each presence type is, warmest first. Drives CSV / JSON ordering.
PRESENCE_RANK = {"none": 0, "social": 1, "builder": 2}

BUSINESS_TYPES = [
    "barber shop", "nail salon", "hair salon", "auto repair shop",
    "auto body shop", "landscaping company", "lawn care service",
    "house cleaning service", "daycare center", "home health care agency",
    "dental office", "chiropractor", "massage therapist", "tailor",
    "locksmith", "moving company", "junk removal service",
    "pest control service", "HVAC contractor", "plumber", "electrician",
    "roofing contractor", "catering service", "photography studio",
    "car detailing", "tax preparation service", "notary public",
    "physical therapy clinic", "podiatrist", "optometrist",
    "veterinary clinic", "pet grooming", "driving school",
    "tutoring service", "event planner",
]

CITIES = {
    "MA": [
        "Springfield MA", "Worcester MA", "Lowell MA", "Brockton MA",
        "New Bedford MA", "Fall River MA", "Lynn MA", "Lawrence MA",
        "Haverhill MA", "Chicopee MA", "Holyoke MA", "Taunton MA",
        "Revere MA", "Everett MA", "Methuen MA", "Fitchburg MA",
        "Pittsfield MA", "Attleboro MA", "Leominster MA", "Chelsea MA",
    ],
    "CT": [
        "Bridgeport CT", "New Haven CT", "Hartford CT", "Waterbury CT",
        "New Britain CT", "Danbury CT", "Norwalk CT", "Meriden CT",
        "Bristol CT", "West Haven CT", "Middletown CT", "Norwich CT",
        "East Hartford CT", "Manchester CT", "Torrington CT",
        "New London CT", "Ansonia CT", "Derby CT", "Naugatuck CT",
        "Enfield CT",
    ],
    "NY": [
        "Yonkers NY", "Buffalo NY", "Rochester NY", "Syracuse NY",
        "Albany NY", "Utica NY", "Schenectady NY", "Binghamton NY",
        "Niagara Falls NY", "Troy NY", "Mount Vernon NY", "New Rochelle NY",
        "White Plains NY", "Hempstead NY", "Freeport NY", "Elmira NY",
        "Poughkeepsie NY", "Newburgh NY", "Rome NY", "Jamestown NY",
        "Bronx NY", "Queens NY", "Brooklyn NY", "Staten Island NY",
    ],
}

MIN_REVIEWS = 3
SLEEP_BETWEEN = 0.3
OUTFILE = "no_website_leads.csv"
PROFILE_OUTFILE = "lead_profiles.json"

# Local tally of billed requests per month, per SKU, so repeated runs stay
# inside Google's free tier. Gitignored. See MONTHLY_FREE_LIMIT / --monthly-limit.
USAGE_FILE = ".api_usage.json"
MONTHLY_FREE_LIMIT = 1000  # free requests/month, per SKU (the two SKUs don't pool)

# Resume cache (--resume). Remembers which queries are fully swept and which
# place IDs we've already captured, so a re-run spends calls only on new
# ground. Per Google's terms we only persist place IDs (cacheable indefinitely)
# and phone numbers for dedupe — never the rich fields. Gitignored.
SEEN_FILE = ".seen_places.json"


def load_dotenv(path=".env"):
    """Populate os.environ from a .env file next to the script, if present.

    Kept deliberately tiny: the project depends on the standard library plus
    requests only, so we don't pull in python-dotenv. A real environment
    variable always wins over a .env line, so `export KEY=...` still overrides.
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):  # tolerate `export KEY=value`
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def classify_presence(website):
    """Bucket a listing by its (missing) web presence.

    Returns one of: "none" (no link at all), "social" (only a Facebook/IG/etc
    page), "builder" (a Google auto-generated stub) or "website" (a real site).
    Only the first three are leads. Matching on the domain suffix catches
    subdomains like m.facebook.com or a business's sites.google.com page.
    """
    if not website:
        return "none"
    host = urlparse(website).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if _host_in(host, SOCIAL_DOMAINS):
        return "social"
    if _host_in(host, BUILDER_DOMAINS):
        return "builder"
    return "website"


def _host_in(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


# --- monthly free-tier tracking -------------------------------------------
# Google bills each request against a per-SKU free allowance that resets
# monthly. We keep a local count so repeated runs never quietly cross it. The
# guard assumes this script is the only thing spending on that SKU for the
# project — if you share the key, check the real number in Cloud Console.

def current_month():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def load_usage(path=USAGE_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_usage(usage, path=USAGE_FILE):
    # Write-then-rename so an interrupt can't corrupt the count and lose track.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(usage, f, indent=2)
    os.replace(tmp, path)


def month_used(usage, month, sku):
    return usage.get(month, {}).get(sku, 0)


def record_call(usage, month, sku):
    usage.setdefault(month, {})[sku] = month_used(usage, month, sku) + 1
    save_usage(usage)


# --- resume cache ----------------------------------------------------------

def load_cache(path=SEEN_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    data.setdefault("queries_done", {})  # query string -> ISO timestamp
    data.setdefault("places", {})        # place_id -> phone (dedupe only)
    return data


def save_cache(cache, path=SEEN_FILE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, path)


def search(api_key, query, field_mask, page_token=None):
    """Return (places, next_page_token, billed).

    `billed` is True only for a 200 response — the case Google charges for and
    the only case the monthly counter should advance on.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    body = {"textQuery": query, "languageCode": "en"}
    if page_token:
        body["pageToken"] = page_token

    try:
        resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=30)
    except requests.RequestException as exc:
        print(f"  ! network error: {exc}", file=sys.stderr)
        return [], None, False

    if resp.status_code != 200:
        print(f"  ! HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        return [], None, False

    data = resp.json()
    return data.get("places", []), data.get("nextPageToken"), True


def is_lead(place, min_reviews):
    # A real website disqualifies; a social/builder-only link does not — those
    # are still prospects, just a different pitch. classify_presence sorts them.
    if classify_presence(place.get("websiteUri")) == "website":
        return False
    if place.get("businessStatus") != "OPERATIONAL":
        return False
    if not place.get("nationalPhoneNumber"):
        return False
    if place.get("userRatingCount", 0) < min_reviews:
        return False
    return True


def to_row(place, state, city, biz_type):
    website = place.get("websiteUri", "")
    return {
        "name": place.get("displayName", {}).get("text", ""),
        "phone": place.get("nationalPhoneNumber", ""),
        "address": place.get("formattedAddress", ""),
        "state": state,
        "city": city,
        "category": place.get("primaryTypeDisplayName", {}).get("text", biz_type),
        "rating": place.get("rating", ""),
        "review_count": place.get("userRatingCount", 0),
        "presence": classify_presence(website),
        "existing_link": website,
        "google_maps_url": place.get("googleMapsUri", ""),
    }


def _review(r):
    return {
        "author": r.get("authorAttribution", {}).get("displayName", ""),
        "rating": r.get("rating", ""),
        "text": (r.get("text", {}).get("text")
                 or r.get("originalText", {}).get("text", "")),
        "when": r.get("relativePublishTimeDescription", ""),
    }


def to_profile(place, row):
    """Everything an agent needs to mock up a site for this business.

    Name, category and services frame the copy; hours, address and phone are
    the contact block; location feeds a map; reviews become testimonials; any
    existing social link is a branding cue.
    """
    return {
        "place_id": place.get("id", ""),
        "name": row["name"],
        "category": row["category"],
        "primary_type": place.get("primaryType", ""),
        "services": place.get("types", []),
        "phone": row["phone"],
        "address": row["address"],
        "short_address": place.get("shortFormattedAddress", ""),
        "city": row["city"],
        "state": row["state"],
        "location": place.get("location", {}),
        "rating": row["rating"],
        "review_count": row["review_count"],
        "price_level": place.get("priceLevel", ""),
        "presence": row["presence"],
        "existing_link": row["existing_link"],
        "hours": place.get("regularOpeningHours", {}).get("weekdayDescriptions", []),
        "description": place.get("editorialSummary", {}).get("text", ""),
        "reviews": [_review(r) for r in place.get("reviews", [])],
        "photo_names": [ph.get("name", "") for ph in place.get("photos", [])],
        "google_maps_url": row["google_maps_url"],
    }


def run_test(api_key, min_reviews, monthly_limit):
    """One API call. Confirms the key, billing and field mask all work."""
    month = current_month()
    usage = load_usage()
    used = month_used(usage, month, "base")
    if used >= monthly_limit:
        print(f"Monthly free-tier limit reached: {used}/{monthly_limit} base-tier "
              f"requests already used in {month}. Not spending a test call.")
        return 1

    print("Test run: 1 API call to 'barber shop in Springfield MA'\n")
    places, _, billed = search(api_key, "barber shop in Springfield MA", BASE_FIELD_MASK)
    if billed:
        record_call(usage, month, "base")

    if not places:
        print("No results. Check that Places API (New) is enabled and billing is on.")
        return 1

    no_site = [p for p in places if is_lead(p, min_reviews)]
    print(f"Returned {len(places)} businesses. {len(no_site)} have no real website.\n")
    for p in no_site[:5]:
        name = p.get("displayName", {}).get("text", "?")
        phone = p.get("nationalPhoneNumber", "no phone")
        presence = classify_presence(p.get("websiteUri"))
        print(f"  [{presence:<7}] {name} - {phone}")
    print(f"\nKey works ({used + 1}/{monthly_limit} base-tier requests used this "
          f"month). Run without --test to do a real sweep.")
    return 0


def _sort_key(row):
    return (PRESENCE_RANK.get(row["presence"], 9),
            row["state"], -int(row["review_count"] or 0))


def write_csv(leads, append=False):
    rows = sorted(leads.values(), key=_sort_key)
    cols = ["name", "phone", "address", "state", "city", "category",
            "rating", "review_count", "presence", "existing_link",
            "google_maps_url"]
    # In --resume mode we append new leads to the existing file so a growing
    # pipeline (and any outreach columns you add by hand) is never clobbered.
    existing = append and os.path.exists(OUTFILE)
    with open(OUTFILE, "a" if existing else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        if not existing:
            writer.writeheader()
        writer.writerows(rows)


def write_profiles(profiles):
    leads = sorted(profiles.values(), key=_sort_key)
    payload = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "lead_count": len(leads),
        "purpose": "Per-lead data for an agent to build a mock website to pitch.",
        "leads": leads,
    }
    with open(PROFILE_OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def report(leads, checked, calls, wrote_profiles):
    by_state, by_presence = {}, {}
    for row in leads.values():
        by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        by_presence[row["presence"]] = by_presence.get(row["presence"], 0) + 1
    print("\n" + "=" * 45)
    print(f"Businesses checked : {checked}")
    print(f"API calls made     : {calls}")
    print(f"Leads found        : {len(leads)}")
    for presence in ("none", "social", "builder"):
        if by_presence.get(presence):
            print(f"  {presence:<7}: {by_presence[presence]}")
    for state, count in sorted(by_state.items()):
        print(f"  {state}: {count}")
    print(f"Saved to           : {OUTFILE}")
    if wrote_profiles:
        print(f"Profiles saved to  : {PROFILE_OUTFILE}")
    # Closing divider is printed by the caller, after the monthly-usage line.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true",
                    help="single API call to verify setup")
    ap.add_argument("--target", type=int, default=200,
                    help="stop after this many leads (0 = no limit)")
    ap.add_argument("--state", choices=["MA", "CT", "NY"],
                    help="limit to one state")
    ap.add_argument("--max-pages", type=int, default=2,
                    help="pages per query, 20 results each")
    ap.add_argument("--max-calls", type=int, default=400,
                    help="hard ceiling on API calls, protects your bill")
    ap.add_argument("--min-reviews", type=int, default=MIN_REVIEWS,
                    help="minimum review count to keep a listing (default %(default)s); "
                         "lower it to catch small-city businesses with 1-2 reviews")
    ap.add_argument("--profiles", action="store_true",
                    help="also scrape rich per-lead data (reviews, hours, description, "
                         "services, location) to lead_profiles.json for building mock "
                         "sites. NOTE: uses Google's Enterprise+Atmosphere field tier "
                         "(~$40/1000 vs ~$35), so only turn it on for real batches.")
    ap.add_argument("--monthly-limit", type=int, default=MONTHLY_FREE_LIMIT,
                    help="never make more than this many billed requests per calendar "
                         "month (default %(default)s = the free tier). Counted per SKU "
                         "in .api_usage.json and enforced across every run, so you stay "
                         "inside the free tier. Raise it to spend on purpose.")
    ap.add_argument("--resume", action="store_true",
                    help="skip queries already fully swept in a previous run (cached in "
                         ".seen_places.json) and skip businesses you already captured, so "
                         "a re-run spends its budget only on new ground. New leads are "
                         "appended to the CSV. Pair with --monthly-limit to sweep a big "
                         "area across several months without ever re-paying.")
    ap.add_argument("--reset-cache", action="store_true",
                    help="delete the resume cache (.seen_places.json) and start fresh.")
    args = ap.parse_args()

    if args.reset_cache:
        try:
            os.remove(SEEN_FILE)
            print(f"Cleared resume cache {SEEN_FILE}.")
        except FileNotFoundError:
            print(f"No resume cache at {SEEN_FILE} to clear.")

    load_dotenv()  # pull GOOGLE_PLACES_API_KEY from .env if it isn't already set

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        sys.exit("Set GOOGLE_PLACES_API_KEY (in the environment or a .env file) first.")

    if args.test:
        sys.exit(run_test(api_key, args.min_reviews, args.monthly_limit))

    field_mask = PROFILE_FIELD_MASK if args.profiles else BASE_FIELD_MASK
    cities = CITIES if not args.state else {args.state: CITIES[args.state]}

    # The two field tiers are separate SKUs with separate free allowances, so
    # track them under separate keys.
    sku = "atmosphere" if args.profiles else "base"
    month = current_month()
    usage = load_usage()
    used_before = month_used(usage, month, sku)
    budget = args.monthly_limit - used_before  # calls left before we'd be billed
    if budget <= 0:
        sys.exit(f"Monthly free-tier limit reached: {used_before}/{args.monthly_limit} "
                 f"{sku}-tier requests used in {month}. Nothing spent. Wait for the "
                 f"month to reset, or raise --monthly-limit to spend beyond the free tier.")

    # The run stops at whichever comes first: this run's --max-calls, or the
    # month's remaining free budget. That's what keeps cumulative usage in-tier.
    ceiling = min(args.max_calls, budget)
    monthly_bound = budget <= args.max_calls

    cache = load_cache() if args.resume else {"queries_done": {}, "places": {}}
    leads, profiles, checked, calls = {}, {}, 0, 0
    skipped_queries, skipped_seen = 0, 0

    def save_all():
        write_csv(leads, append=args.resume)
        if args.profiles:
            write_profiles(profiles)
        report(leads, checked, calls, args.profiles)
        if args.resume:
            print(f"Resume             : skipped {skipped_queries} done queries, "
                  f"{skipped_seen} already-seen businesses")
        used_now = used_before + calls
        left = max(0, args.monthly_limit - used_now)
        print(f"Monthly {sku}-tier usage : {used_now}/{args.monthly_limit} "
              f"in {month} ({left} free left)")
        print("=" * 45)

    for state, city_list in cities.items():
        for city in city_list:
            for biz_type in BUSINESS_TYPES:
                query = f"{biz_type} in {city}"

                # Already fully swept in a past run? Skip it — costs no calls.
                if args.resume and query in cache["queries_done"]:
                    skipped_queries += 1
                    continue

                if calls >= ceiling:
                    if monthly_bound:
                        print(f"\nStopping to stay in the free tier: reached "
                              f"{used_before + calls}/{args.monthly_limit} {sku}-tier "
                              f"requests for {month}.")
                    else:
                        print(f"\nHit per-run call ceiling of {args.max_calls}.")
                    save_all()
                    return

                token = None
                stopped_early = False
                for _ in range(args.max_pages):
                    if calls >= ceiling:  # re-check before every billed request
                        stopped_early = True
                        break
                    places, token, billed = search(api_key, query, field_mask, token)
                    if not billed:
                        stopped_early = True
                        break
                    calls += 1
                    record_call(usage, month, sku)
                    checked += len(places)
                    for p in places:
                        if not is_lead(p, args.min_reviews):
                            continue
                        pid = p.get("id", "")
                        # Captured in an earlier run? Don't re-emit it.
                        if args.resume and pid and pid in cache["places"]:
                            skipped_seen += 1
                            continue
                        row = to_row(p, state, city, biz_type)
                        if row["phone"] in leads:  # within-run dedupe
                            continue
                        leads[row["phone"]] = row
                        if args.profiles:
                            profiles[row["phone"]] = to_profile(p, row)
                        if args.resume and pid:
                            cache["places"][pid] = row["phone"]
                    if not token:
                        break
                    time.sleep(SLEEP_BETWEEN)

                # Mark done only if we swept every page we meant to (not cut off
                # by the ceiling or an error) — so a resumed run redoes it cleanly.
                if args.resume and not stopped_early:
                    cache["queries_done"][query] = \
                        datetime.datetime.now(datetime.timezone.utc).isoformat()
                    save_cache(cache)

                time.sleep(SLEEP_BETWEEN)

                if args.target and len(leads) >= args.target:
                    print(f"\nHit target of {args.target} leads.")
                    save_all()
                    return

            print(f"{city}: {len(leads)} leads / {calls} calls "
                  f"({used_before + calls}/{args.monthly_limit} this month)")

    save_all()


if __name__ == "__main__":
    main()
