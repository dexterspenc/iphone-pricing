"""
pipeline.py — Orchestrator: scrape -> parse -> save to Google Sheets.

Usage
-----
    # Full run (scrape live + append new rows)
    python scraper/pipeline.py

    # Dry-run using cached raw_captions.json (no Instagram login needed)
    python scraper/pipeline.py --cached

    # Limit to N most-recent posts when scraping live
    python scraper/pipeline.py --max-posts 50
"""

import argparse
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Make sure sibling modules and api/ helpers are importable from repo root
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from scraper import scrape_profile, load_cached_captions
from parser import parse_caption
from _gsheets import get_sheet

load_dotenv()

SHEET_NAME = "listings"

# Column order must match the header row in the Google Sheet exactly.
# Mirrors the Supabase schema from migrations/001_create_listings.sql,
# with battery_replaced and has_aftermarket_part appended at the end
# (they were never added to Supabase but are present in parsed dicts).
SHEET_COLUMNS = [
    "id",
    "date_posted",
    "series",
    "variant",
    "model",
    "storage_gb",
    "color",
    "battery_health",
    "physical_condition",
    "origin_type",
    "regional_code",
    "garansi_aktif",
    "garansi_expired_fullset",
    "has_box",
    "has_charger",
    "has_manual",
    "face_id_ok",
    "lcd_original",
    "battery_replaced",
    "has_aftermarket_part",
    "price_idr",
    "source_code",
    "notes",
    "created_at",
]


# ---------------------------------------------------------------------------
# Dedup check
# ---------------------------------------------------------------------------

def _fetch_existing_source_codes(sheet) -> set[str]:
    """
    Return the set of source_codes already in the sheet.
    Fetches only the source_code column to minimise data transfer.
    """
    headers = sheet.row_values(1)
    if "source_code" not in headers:
        return set()

    col_idx = headers.index("source_code") + 1   # gspread is 1-indexed
    values  = sheet.col_values(col_idx)
    return {v for v in values[1:] if v}           # skip header row


# ---------------------------------------------------------------------------
# Row serialisation
# ---------------------------------------------------------------------------

def _listing_to_row(listing: dict) -> list:
    """Convert a parsed listing dict to an ordered list matching SHEET_COLUMNS."""
    now = datetime.now(timezone.utc).isoformat()

    def _bool(v) -> str:
        """Sheets stores booleans as TRUE/FALSE strings."""
        if v is None:
            return ""
        return "TRUE" if v else "FALSE"

    def _date(v) -> str:
        return str(v) if v is not None else ""

    return [
        str(uuid.uuid4()),                                     # id
        _date(listing.get("date_posted")),                     # date_posted
        listing.get("series")             or "",               # series
        listing.get("variant")            or "",               # variant
        listing.get("model")              or "",               # model
        listing.get("storage_gb")         or "",               # storage_gb
        listing.get("color")              or "",               # color
        listing.get("battery_health")     or "",               # battery_health
        listing.get("physical_condition") or "",               # physical_condition
        listing.get("origin_type")        or "",               # origin_type
        listing.get("regional_code")      or "",               # regional_code
        _bool(listing.get("garansi_aktif")),                   # garansi_aktif
        _date(listing.get("garansi_expired_fullset")),         # garansi_expired_fullset
        _bool(listing.get("has_box")),                         # has_box
        _bool(listing.get("has_charger")),                     # has_charger
        _bool(listing.get("has_manual")),                      # has_manual
        _bool(listing.get("face_id_ok")),                      # face_id_ok
        _bool(listing.get("lcd_original")),                    # lcd_original
        _bool(listing.get("battery_replaced")),                # battery_replaced
        _bool(listing.get("has_aftermarket_part")),            # has_aftermarket_part
        listing.get("price_idr")          or "",               # price_idr
        listing.get("source_code")        or "",               # source_code
        listing.get("notes")              or "",               # notes
        now,                                                   # created_at
    ]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    use_cached: bool = False,
    since: Optional[date] = None,
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
        effective_since = since or date(2025, 8, 1)
        print(f"[pipeline] Scraping @cherishcomapple ({effective_since.isoformat()} -> today) ...")
        raw_records = scrape_profile(since=effective_since)

    print(f"[pipeline] {len(raw_records)} raw posts loaded.")

    # 2. Connect to Google Sheets ----------------------------------------
    sheet = get_sheet(SHEET_NAME)
    existing_codes = _fetch_existing_source_codes(sheet)
    print(f"[pipeline] {len(existing_codes)} source_codes already in sheet.")

    # 3. Parse + filter duplicates ---------------------------------------
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

    # 4. Append to Google Sheets -----------------------------------------
    if not new_listings:
        print("[pipeline] Nothing to insert. Done.")
        return

    BATCH_SIZE = 50
    inserted = 0

    for i in range(0, len(new_listings), BATCH_SIZE):
        batch = new_listings[i : i + BATCH_SIZE]
        rows  = [_listing_to_row(listing) for listing in batch]
        sheet.append_rows(rows, value_input_option="RAW")
        inserted += len(rows)

    print("=" * 60)
    print(f"[pipeline] DONE — {inserted} new listings appended to Google Sheets.")
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
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Earliest post date to scrape (default: 2025-08-01)",
    )
    args = parser.parse_args()

    run_pipeline(use_cached=args.cached, since=args.since)
