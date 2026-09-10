# No-Website Lead Finder

Finds service businesses in MA, CT and NY that have a Google Business Profile
but no website. Outputs a CSV you can pitch from.

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

## Cost

The field mask asks for website, phone and rating, which puts Text Search in
Google's Enterprise tier: about 1,000 free requests per month, then roughly
$35 per 1,000. Each request returns up to 20 businesses, so the free tier
covers about 20,000 businesses a month.

Set a budget alert anyway: Google Cloud Console -> Billing -> Budgets & alerts.

## Tuning

Edit `BUSINESS_TYPES` and `CITIES` at the top of the script. `MIN_REVIEWS`
(default 3) filters out dead listings; override it per run with
`--min-reviews`. Lower it to catch legitimate small-city businesses that only
have one or two reviews:

    python no_website_leads.py --state CT --min-reviews 1
