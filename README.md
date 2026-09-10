# No-Website Lead Finder

Finds service businesses in MA, CT and NY that have a Google Business Profile
but no website. Outputs a CSV you can pitch from.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_PLACES_API_KEY="your_key"

## Verify your key first

    python no_website_leads.py --test

One API call. Confirms the key, billing and field mask are working before
you spend anything on a real sweep.

## Real runs

    python no_website_leads.py --target 50
    python no_website_leads.py --state CT --target 100
    python no_website_leads.py --target 0 --max-calls 800

`--max-calls` is a hard ceiling so a bad loop can't run up your bill.

## Cost

The field mask asks for website, phone and rating, which puts Text Search in
Google's Enterprise tier: about 1,000 free requests per month, then roughly
$35 per 1,000. Each request returns up to 20 businesses, so the free tier
covers about 20,000 businesses a month.

Set a budget alert anyway: Google Cloud Console -> Billing -> Budgets & alerts.

## Tuning

Edit `BUSINESS_TYPES` and `CITIES` at the top of the script. `MIN_REVIEWS`
filters out dead listings.
