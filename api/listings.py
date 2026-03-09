"""api/listings.py — GET /api/listings"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/listings")
def listings(limit: int = 50, series: Optional[int] = None, variant: Optional[str] = None):
    from supabase import create_client
    client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    q = client.table("listings").select(
        "id,date_posted,series,variant,model,storage_gb,color,"
        "battery_health,physical_condition,origin_type,regional_code,"
        "garansi_aktif,price_idr,source_code"
    ).order("date_posted", desc=True).limit(limit)
    if series:
        q = q.eq("series", series)
    if variant:
        q = q.eq("variant", variant)
    return {"data": q.execute().data}
