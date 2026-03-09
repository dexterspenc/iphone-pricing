"""
scraper.py — Apify-based scraper for @cherishcomapple.

Uses the Apify Instagram Scraper actor (apify/instagram-scraper) to fetch
posts from 2026-01-01 up to today. Raw captions are saved to
raw_captions.json as a backup for pipeline resume.

Requires APIFY_API_TOKEN in .env.
"""

import json
import os
import time
from datetime import date
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

TARGET_PROFILE  = "cherishcomapple"
RAW_OUTPUT_FILE = Path(__file__).parent / "raw_captions.json"
START_DATE      = date(2025, 8, 1)

# Apify actor for Instagram scraping
ACTOR_ID = "apify/instagram-scraper"


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

def scrape_profile(
    resume_from_json: bool = True,
    since: date = START_DATE,
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
    """
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
