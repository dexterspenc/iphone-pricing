"""api/predict.py — POST /api/predict"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from _shared import make_verdict
from model.predict import predict_range

app = FastAPI()
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


class PredictRequest(BaseModel):
    series: int
    variant: str = "Regular"
    storage_gb: int = 128
    battery_health: int = 100
    physical_condition: int = 95
    origin_type: str = "iBox"
    regional_code: str = "PA/A"
    garansi_aktif: bool = False
    garansi_expired_fullset: Optional[str] = None
    has_box: bool = True
    has_charger: bool = True
    has_manual: bool = True
    face_id_ok: bool = True
    lcd_original: bool = True
    battery_replaced: bool = False
    has_aftermarket_part: bool = False
    listing_price: Optional[int] = None


@app.post("/api/predict")
def predict(req: PredictRequest):
    result = predict_range(
        series=req.series,
        variant=req.variant,
        storage_gb=req.storage_gb,
        battery_health=req.battery_health,
        physical_condition=req.physical_condition,
        origin_type=req.origin_type,
        regional_code=req.regional_code,
        garansi_aktif=req.garansi_aktif,
        garansi_expired_fullset=req.garansi_expired_fullset,
        has_box=req.has_box,
        has_charger=req.has_charger,
        has_manual=req.has_manual,
        face_id_ok=req.face_id_ok,
        lcd_original=req.lcd_original,
        battery_replaced=req.battery_replaced,
        has_aftermarket_part=req.has_aftermarket_part,
    )
    if req.listing_price:
        result["verdict"] = make_verdict(
            req.listing_price, result["low_idr"], result["high_idr"], result["predicted_idr"]
        )
    return result
