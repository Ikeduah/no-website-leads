#!/usr/bin/env python3
"""
Find service businesses in MA / CT / NY with NO website on Google.

Usage:
    python no_website_leads.py --test           # 1 API call, verify key works
    python no_website_leads.py --target 50      # small real run
    python no_website_leads.py --state CT       # one state only
    python no_website_leads.py                  # full default run
"""

import argparse
import csv
import os
import sys
import time

import requests

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "places.googleMapsUri",
    "nextPageToken",
])

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


def search(api_key, query, page_token=None):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {"textQuery": query, "languageCode": "en"}
    if page_token:
        body["pageToken"] = page_token

    try:
        resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=30)
    except requests.RequestException as exc:
        print(f"  ! network error: {exc}", file=sys.stderr)
        return [], None

    if resp.status_code != 200:
        print(f"  ! HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        return [], None

    data = resp.json()
    return data.get("places", []), data.get("nextPageToken")


def is_lead(place, min_reviews):
    if place.get("websiteUri"):
        return False
    if place.get("businessStatus") != "OPERATIONAL":
        return False
    if not place.get("nationalPhoneNumber"):
        return False
    if place.get("userRatingCount", 0) < min_reviews:
        return False
    return True


def to_row(place, state, city, biz_type):
    return {
        "name": place.get("displayName", {}).get("text", ""),
        "phone": place.get("nationalPhoneNumber", ""),
        "address": place.get("formattedAddress", ""),
        "state": state,
        "city": city,
        "category": place.get("primaryTypeDisplayName", {}).get("text", biz_type),
        "rating": place.get("rating", ""),
        "review_count": place.get("userRatingCount", 0),
        "google_maps_url": place.get("googleMapsUri", ""),
    }


def run_test(api_key, min_reviews):
    """One API call. Confirms the key, billing and field mask all work."""
    print("Test run: 1 API call to 'barber shop in Springfield MA'\n")
    places, _ = search(api_key, "barber shop in Springfield MA")

    if not places:
        print("No results. Check that Places API (New) is enabled and billing is on.")
        return 1

    no_site = [p for p in places if is_lead(p, min_reviews)]
    print(f"Returned {len(places)} businesses. {len(no_site)} have no website.\n")
    for p in no_site[:5]:
        name = p.get("displayName", {}).get("text", "?")
        phone = p.get("nationalPhoneNumber", "no phone")
        print(f"  {name} - {phone}")
    print("\nKey works. Run without --test to do a real sweep.")
    return 0


def write_csv(leads):
    rows = sorted(leads.values(),
                  key=lambda r: (r["state"], -int(r["review_count"] or 0)))
    cols = ["name", "phone", "address", "state", "city",
            "category", "rating", "review_count", "google_maps_url"]
    with open(OUTFILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def report(leads, checked, calls):
    by_state = {}
    for row in leads.values():
        by_state[row["state"]] = by_state.get(row["state"], 0) + 1
    print("\n" + "=" * 45)
    print(f"Businesses checked : {checked}")
    print(f"API calls made     : {calls}")
    print(f"Leads found        : {len(leads)}")
    for state, count in sorted(by_state.items()):
        print(f"  {state}: {count}")
    print(f"Saved to           : {OUTFILE}")
    print("=" * 45)


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
    args = ap.parse_args()

    load_dotenv()  # pull GOOGLE_PLACES_API_KEY from .env if it isn't already set

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        sys.exit("Set GOOGLE_PLACES_API_KEY (in the environment or a .env file) first.")

    if args.test:
        sys.exit(run_test(api_key, args.min_reviews))

    cities = CITIES if not args.state else {args.state: CITIES[args.state]}
    leads, checked, calls = {}, 0, 0

    for state, city_list in cities.items():
        for city in city_list:
            for biz_type in BUSINESS_TYPES:
                if calls >= args.max_calls:
                    print(f"\nHit call ceiling of {args.max_calls}.")
                    write_csv(leads)
                    report(leads, checked, calls)
                    return

                token = None
                for _ in range(args.max_pages):
                    places, token = search(api_key, f"{biz_type} in {city}", token)
                    calls += 1
                    checked += len(places)
                    for p in places:
                        if is_lead(p, args.min_reviews):
                            row = to_row(p, state, city, biz_type)
                            leads.setdefault(row["phone"], row)
                    if not token:
                        break
                    time.sleep(SLEEP_BETWEEN)

                time.sleep(SLEEP_BETWEEN)

                if args.target and len(leads) >= args.target:
                    print(f"\nHit target of {args.target} leads.")
                    write_csv(leads)
                    report(leads, checked, calls)
                    return

            print(f"{city}: {len(leads)} leads / {calls} calls")

    write_csv(leads)
    report(leads, checked, calls)


if __name__ == "__main__":
    main()
