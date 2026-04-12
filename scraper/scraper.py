"""
scraper.py — Apify-based scraper for @cherishcomapple.

Uses the Apify Instagram Scraper actor (apify/instagram-scraper) to fetch
posts from a given date up to today. Raw captions are saved to
raw_captions.json as a backup for pipeline resume.

Requires APIFY_API_TOKEN in .env.
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

# Make api/ importable for _gsheets helper
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

TARGET_PROFILE  = "cherishcomapple"
RAW_OUTPUT_FILE = Path(__file__).parent / "raw_captions.json"
FALLBACK_START  = date(2025, 11, 1)   # used when no data found (first-time setup)

# Apify actor for Instagram scraping
ACTOR_ID = "apify/instagram-scraper"


def _get_since_from_sheets() -> date:
    """Return MAX(date_posted) from Google Sheets, or FALLBACK_START if sheet is empty."""
    try:
        from _gsheets import get_sheet
        sheet = get_sheet("listings")
        headers = sheet.row_values(1)
        if "date_posted" not in headers:
            print(f"[scraper] 'date_posted' column not found in sheet — using fallback {FALLBACK_START}.")
            return FALLBACK_START
        col_idx = headers.index("date_posted") + 1  # gspread is 1-indexed
        values = sheet.col_values(col_idx)[1:]       # skip header
        dates = [v for v in values if v]
        if dates:
            latest = date.fromisoformat(max(dates))
            print(f"[scraper] Latest date_posted in Google Sheets: {latest}. Using as scrape start.")
            return latest
    except Exception as e:
        print(f"[scraper] Could not query Google Sheets ({e}) — using fallback start date {FALLBACK_START}.")
    print(f"[scraper] No rows in Google Sheets — using fallback start date {FALLBACK_START}.")
    return FALLBACK_START


def _get_since_from_supabase() -> date:
    """Return MAX(date_posted) from Supabase listings, or FALLBACK_START if table is empty.

    Kept as a fallback. Supabase import is lazy to avoid ImportError if the
    package is not installed.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print(f"[scraper] Supabase creds not set — using fallback start date {FALLBACK_START}.")
        return FALLBACK_START
    try:
        from supabase import create_client  # lazy — supabase may not be installed
        client = create_client(url, key)
        resp = client.table("listings").select("date_posted").order("date_posted", desc=True).limit(1).execute()
        if resp.data and resp.data[0].get("date_posted"):
            latest = date.fromisoformat(resp.data[0]["date_posted"])
            print(f"[scraper] Latest date_posted in Supabase: {latest}. Using as scrape start.")
            return latest
    except ImportError:
        print(f"[scraper] supabase package not installed — using fallback start date {FALLBACK_START}.")
    except Exception as e:
        print(f"[scraper] Could not query Supabase ({e}) — using fallback start date {FALLBACK_START}.")
    print(f"[scraper] No rows in Supabase — using fallback start date {FALLBACK_START}.")
    return FALLBACK_START


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

def scrape_profile(
    resume_from_json: bool = True,
    since: date | None = None,
) -> list[dict]:
    """
    Run the Apify Instagram Scraper actor for @cherishcomapple and return
    posts on or after ``since`` as a list of dicts with keys:
    ``shortcode``, ``date_posted`` (ISO string), ``caption``.

    Parameters
    ----------
    resume_from_json : If True and raw_captions.json exists, merge new
                       results with the existing cache (dedup by shortcode).
    since            : Earliest post date to include (inclusive).
                       Defaults to MAX(date_posted) from Google Sheets.
    """
    if since is None:
        since = _get_since_from_sheets()

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise EnvironmentError("APIFY_API_TOKEN must be set in .env")

    client = ApifyClient(api_token)

    # Load existing cache
    already_scraped: set[str] = set()
    existing_records: list[dict] = []
    if resume_from_json and RAW_OUTPUT_FILE.exists():
        try:
            with RAW_OUTPUT_FILE.open("r", encoding="utf-8") as f:
                existing_records = json.load(f)
            already_scraped = {r["shortcode"] for r in existing_records}
            print(f"[scraper] Resuming — {len(already_scraped)} posts already cached.")
        except (json.JSONDecodeError, KeyError):
            pass

    today = date.today()
    print(
        f"[scraper] Starting Apify actor for @{TARGET_PROFILE} "
        f"({since.isoformat()} -> {today.isoformat()}) ..."
    )

    # Actor input — fetch posts only from the target date window
    actor_input = {
        "directUrls":        [f"https://www.instagram.com/{TARGET_PROFILE}/"],
        "resultsType":       "posts",
        "resultsLimit":      3000,         # ~14 posts/day * 210 days (Aug-Mar) = ~2940
        "addParentData":     False,
        "onlyPostsNewerThan": since.isoformat(),  # ISO date cutoff
    }

    # Run actor synchronously (blocks until finished)
    run = client.actor(ACTOR_ID).call(run_input=actor_input)

    print(f"[scraper] Actor run finished. Dataset ID: {run['defaultDatasetId']}")

    # Iterate dataset items
    records: list[dict] = list(existing_records)
    new_count = 0

    dataset_items = client.dataset(run["defaultDatasetId"]).iterate_items()
    for item in dataset_items:
        shortcode = item.get("shortCode") or item.get("id", "")

        # Parse post date from Apify's timestamp field
        raw_ts = item.get("timestamp") or item.get("takenAtTs") or ""
        try:
            if isinstance(raw_ts, (int, float)):
                date_posted = date.fromtimestamp(raw_ts)
            else:
                date_posted = date.fromisoformat(str(raw_ts)[:10])
        except (ValueError, TypeError, OSError):
            date_posted = today  # fallback

        # Hard cutoff — skip posts before since
        if date_posted < since:
            continue

        if shortcode in already_scraped:
            continue

        caption = item.get("caption") or item.get("alt") or ""

        records.append({
            "shortcode":   shortcode,
            "date_posted": date_posted.isoformat(),
            "caption":     caption,
        })
        already_scraped.add(shortcode)
        new_count += 1

    _save_json(records)
    print(f"[scraper] Done. {new_count} new posts scraped. Total in cache: {len(records)}.")
    return records


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

def _save_json(records: list[dict]) -> None:
    RAW_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RAW_OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def load_cached_captions() -> list[dict]:
    """Load previously-scraped captions from raw_captions.json."""
    if not RAW_OUTPUT_FILE.exists():
        return []
    with RAW_OUTPUT_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    records = scrape_profile()
    print(f"Total records: {len(records)}")
