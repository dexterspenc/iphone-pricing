"""
scripts/setup_sheets.py — One-time setup: write header row to the "listings" sheet.

Usage:
    python scripts/setup_sheets.py
"""
import sys
from pathlib import Path

# Resolve paths so imports work regardless of where the script is called from
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "api"))      # for _gsheets
sys.path.insert(0, str(ROOT / "scraper"))  # for pipeline.SHEET_COLUMNS

from _gsheets import get_sheet
from pipeline import SHEET_COLUMNS


def main() -> None:
    print("Connecting to Google Sheets...")
    try:
        sheet = get_sheet("listings")
    except EnvironmentError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Could not open sheet: {exc}")
        sys.exit(1)

    first_row = sheet.row_values(1)
    if first_row:
        print(f"Header already exists: {first_row}")
        return

    sheet.insert_row(SHEET_COLUMNS, index=1)
    print(f"[OK] Header row written ({len(SHEET_COLUMNS)} columns):")
    print("     " + ", ".join(SHEET_COLUMNS))


if __name__ == "__main__":
    main()
