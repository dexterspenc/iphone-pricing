"""
predict.py — Predict iPhone resale price using the trained GBR model.

Usage
-----
    from model.predict import predict_price, predict_range

    result = predict_range(series=16, variant="Pro Max", storage_gb=256, ...)
"""

from datetime import date
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).parent.parent))
from model.train import FEATURES, ENC_PATH, META_PATH, MODEL_PATH, engineer_features

import json
import pandas as pd


_cache: dict = {}


def _load():
    if not _cache:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"No trained model found at {MODEL_PATH}. "
                "Run: python model/train.py"
            )
        _cache["model"]    = joblib.load(MODEL_PATH)
        _cache["encoders"] = joblib.load(ENC_PATH)
        with META_PATH.open() as f:
            _cache["meta"] = json.load(f)
    return _cache["model"], _cache["encoders"], _cache["meta"]


def predict_price(
    series: int,
    variant: str = "Regular",
    storage_gb: int = 128,
    battery_health: int = 100,
    physical_condition: int = 95,
    origin_type: str = "iBox",
    regional_code: str = "PA/A",
    garansi_aktif: bool = False,
    garansi_expired_fullset: Optional[str] = None,
    has_box: bool = True,
    has_charger: bool = True,
    has_manual: bool = True,
    face_id_ok: bool = True,
    lcd_original: bool = True,
    battery_replaced: bool = False,
    has_aftermarket_part: bool = False,
    color: str = "Unknown",
) -> float:
    """Return predicted resale price in IDR."""
    model, encoders, _ = _load()

    row = {
        "series":                  series,
        "variant":                 variant,
        "storage_gb":              storage_gb,
        "battery_health":          battery_health,
        "physical_condition":      physical_condition,
        "origin_type":             origin_type,
        "regional_code":           regional_code,
        "garansi_aktif":           garansi_aktif,
        "garansi_expired_fullset": garansi_expired_fullset,
        "has_box":                 has_box,
        "has_charger":             has_charger,
        "has_manual":              has_manual,
        "face_id_ok":              face_id_ok,
        "lcd_original":            lcd_original,
        "battery_replaced":        battery_replaced,
        "has_aftermarket_part":    has_aftermarket_part,
        "color":                   color,
    }

    df_input = pd.DataFrame([row])
    X, _ = engineer_features(df_input, encoders=encoders, fit=False)

    return max(0.0, float(model.predict(X)[0]))


def predict_range(series: int, **kwargs) -> dict:
    """Return predicted price with a +/-15% confidence interval.

    Within-group price std across models is 7-13%, so ±15% covers ~1 sigma
    naturally and avoids excessive false DEAL/OVERPRICE verdicts.
    """
    price = predict_price(series=series, **kwargs)
    return {
        "predicted_idr": round(price, -3),
        "low_idr":        round(price * 0.85, -3),
        "high_idr":       round(price * 1.15, -3),
    }


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    LISTING_PRICE = 17_600_000

    result = predict_range(
        series=16,
        variant="Pro Max",
        storage_gb=256,
        battery_health=98,
        physical_condition=95,
        origin_type="iBox",
        regional_code="SA/A",
        garansi_aktif=True,
        has_box=True,
        has_charger=True,
        has_manual=True,
        face_id_ok=True,
        lcd_original=True,
    )

    predicted = result["predicted_idr"]
    low       = result["low_idr"]
    high      = result["high_idr"]

    if LISTING_PRICE <= low:
        label = "DEAL"
    elif LISTING_PRICE <= high:
        label = "WAJAR"
    else:
        label = "OVERPRICE"

    diff_pct = (LISTING_PRICE - predicted) / predicted * 100

    print(f"Listing price:   IDR {LISTING_PRICE:>15,.0f}")
    print(f"Predicted price: IDR {predicted:>15,.0f}  ({diff_pct:+.1f}% vs listing)")
    print(f"Range (+/-10%):  IDR {low:>15,.0f}  -  IDR {high:,.0f}")
    print(f"Verdict:         {label}")
