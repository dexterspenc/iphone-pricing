"""api/listings.py — GET /api/listings"""
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))        # api/  (for _gsheets)
sys.path.insert(0, str(Path(__file__).parent.parent)) # root

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from _gsheets import get_sheet

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Columns returned in the response — matches the original Supabase SELECT exactly.
_RESPONSE_COLS = {
    "id", "date_posted", "series", "variant", "model", "storage_gb",
    "color", "battery_health", "physical_condition", "origin_type",
    "regional_code", "garansi_aktif", "price_idr", "source_code",
}


def _coerce(record: dict) -> dict:
    """Normalise types that gspread may return as strings."""
    out = {k: v for k, v in record.items() if k in _RESPONSE_COLS}

    # Numeric fields
    for field in ("series", "storage_gb", "battery_health", "physical_condition", "price_idr"):
        raw = out.get(field)
        if raw not in (None, ""):
            try:
                out[field] = int(float(raw))
            except (ValueError, TypeError):
                out[field] = None
        else:
            out[field] = None

    # Boolean field — Sheets stores as TRUE/FALSE strings or Python bool
    raw_garansi = out.get("garansi_aktif")
    if isinstance(raw_garansi, bool):
        out["garansi_aktif"] = raw_garansi
    elif isinstance(raw_garansi, str):
        out["garansi_aktif"] = raw_garansi.upper() == "TRUE"
    else:
        out["garansi_aktif"] = False

    return out


@app.get("/api/listings")
def listings(limit: int = 50, series: Optional[int] = None, variant: Optional[str] = None):
    try:
        sheet = get_sheet("listings")
        data  = sheet.get_all_records()   # list of dicts keyed by header row

        # Filter in Python (equivalent to WHERE series=? AND variant=?)
        if series is not None:
            data = [r for r in data if str(r.get("series", "")) == str(series)]
        if variant:
            data = [r for r in data if r.get("variant") == variant]

        # Sort by date_posted DESC (ISO strings sort correctly lexicographically)
        data.sort(key=lambda r: r.get("date_posted") or "", reverse=True)

        # Slice to limit
        data = data[:limit]

        # Normalise types and trim to response columns
        data = [_coerce(r) for r in data]

        return {"data": data}

    except Exception:
        print(traceback.format_exc())
        raise
