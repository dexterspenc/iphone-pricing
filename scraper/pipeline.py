"""
pipeline.py — Orchestrator: scrape -> parse -> save to Supabase.

Usage
-----
    # Full run (scrape live + upsert)
    python scraper/pipeline.py

    # Dry-run using cached raw_captions.json (no Instagram login needed)
    python scraper/pipeline.py --cached

    # Limit to N most-recent posts when scraping live
    python scraper/pipeline.py --max-posts 50
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

# Make sure sibling modules are importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent))

from scraper import scrape_profile, load_cached_captions
from parser import parse_caption

load_dotenv()

TABLE = "listings"


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _fetch_existing_source_codes(client: Client) -> set[str]:
    """Return the set of source_codes already stored in Supabase."""
    response = client.table(TABLE).select("source_code").execute()
    return {row["source_code"] for row in response.data if row.get("source_code")}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    use_cached: bool = False,
) -> None:
    print("=" * 60)
    print("iPhone Pricing Pipeline")
    print("=" * 60)

    # 1. Scrape / load captions ------------------------------------------
    if use_cached:
        print("[pipeline] Using cached captions from raw_captions.json ...")
        raw_records = load_cached_captions()
        if not raw_records:
            print("[pipeline] No cached captions found. Run without --cached first.")
            return
    else:
        print("[pipeline] Scraping @cherishcomapple (2025-08-01 -> today) ...")
        raw_records = scrape_profile()

    print(f"[pipeline] {len(raw_records)} raw posts loaded.")

    # 2. Connect to Supabase ------------------------------------------------
    client = _get_client()
    existing_codes = _fetch_existing_source_codes(client)
    print(f"[pipeline] {len(existing_codes)} source_codes already in Supabase.")

    # 3. Parse + filter duplicates -----------------------------------------
    new_listings: list[dict] = []
    skipped_duplicates = 0
    skipped_parse_fail = 0

    for record in raw_records:
        caption    = record.get("caption", "")
        raw_date   = record.get("date_posted")
        date_posted: Optional[date] = (
            date.fromisoformat(raw_date) if raw_date else None
        )

        parsed = parse_caption(caption, date_posted=date_posted)

        if parsed is None:
            skipped_parse_fail += 1
            continue

        source_code = parsed.get("source_code")

        if source_code and source_code in existing_codes:
            skipped_duplicates += 1
            continue

        new_listings.append(parsed)

        # Track in-memory to catch duplicates within the same batch
        if source_code:
            existing_codes.add(source_code)

    print(f"[pipeline] {len(new_listings)} new listings to insert.")
    print(f"[pipeline] {skipped_duplicates} skipped (duplicate source_code).")
    print(f"[pipeline] {skipped_parse_fail} skipped (parse failed / not iPhone listing).")

    # 4. Insert to Supabase -------------------------------------------------
    if not new_listings:
        print("[pipeline] Nothing to insert. Done.")
        return

    BATCH_SIZE = 50
    inserted = 0

    for i in range(0, len(new_listings), BATCH_SIZE):
        batch = new_listings[i : i + BATCH_SIZE]
        response = client.table(TABLE).insert(batch).execute()
        inserted += len(response.data)

    print("=" * 60)
    print(f"[pipeline] DONE — {inserted} new listings inserted to Supabase.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iPhone pricing pipeline")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use cached raw_captions.json instead of scraping live",
    )
    args = parser.parse_args()

    run_pipeline(use_cached=args.cached)
