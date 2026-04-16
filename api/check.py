"""api/check.py — POST /api/check"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))   # api/
sys.path.insert(0, str(Path(__file__).parent.parent))  # root

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from _shared import build_result, parse_caption

app = FastAPI()
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


class CheckRequest(BaseModel):
    caption: str
    listing_price: Optional[int] = None


@app.post("/api/check")
def check(req: CheckRequest):
    parsed = parse_caption(req.caption)
    if not parsed or not parsed.get("series"):
        raise HTTPException(status_code=422, detail="Gagal parse caption — bukan listing iPhone yang dikenali.")
    return build_result(parsed, req.listing_price or parsed.get("price_idr"))
