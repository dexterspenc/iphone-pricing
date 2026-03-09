"""
api/_shared.py — Shared helpers for all API functions.
Underscore prefix = not treated as a Vercel serverless function.
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scraper.parser import parse_caption          # noqa: E402
from model.predict import predict_range            # noqa: E402


# ── verdict ───────────────────────────────────────────────────────────────────

def make_verdict(listing_price: int, low: float, high: float, predicted: float) -> dict:
    if listing_price <= low:
        label, emoji = "DEAL", "🔥"
    elif listing_price <= high:
        label, emoji = "WAJAR", "👍"
    else:
        label, emoji = "OVERPRICE", "❌"
    diff_pct = (listing_price - predicted) / predicted * 100
    return {"label": label, "emoji": emoji, "diff_pct": round(diff_pct, 1)}


def build_result(parsed: dict, listing_price: Optional[int]) -> dict:
    result = predict_range(
        series=parsed["series"],
        variant=parsed.get("variant", "Regular"),
        storage_gb=parsed.get("storage_gb") or 128,
        battery_health=parsed.get("battery_health") or 100,
        physical_condition=parsed.get("physical_condition") or 95,
        origin_type=parsed.get("origin_type") or "iBox",
        regional_code=parsed.get("regional_code") or "PA/A",
        garansi_aktif=parsed.get("garansi_aktif", False),
        garansi_expired_fullset=parsed.get("garansi_expired_fullset"),
        has_box=parsed.get("has_box", True),
        has_charger=parsed.get("has_charger", True),
        has_manual=parsed.get("has_manual", True),
        face_id_ok=parsed.get("face_id_ok", True),
        lcd_original=parsed.get("lcd_original", True),
    )
    price_block = {
        "predicted": result["predicted_idr"],
        "low":       result["low_idr"],
        "high":      result["high_idr"],
        "asking":    listing_price,
        "verdict":   None,
    }
    if listing_price:
        price_block["verdict"] = make_verdict(
            listing_price, result["low_idr"], result["high_idr"], result["predicted_idr"]
        )
    return {"specs": parsed, "price": price_block}


# ── Telegram helpers ──────────────────────────────────────────────────────────

def tg_send(chat_id: int, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )


def format_tg_reply(result: dict) -> str:
    specs = result["specs"]
    price = result["price"]

    model  = specs.get("model", "iPhone")
    st     = specs.get("storage_gb", "?")
    color  = specs.get("color", "")
    bh     = specs.get("battery_health", "?")
    origin = specs.get("origin_type", "?")
    rc     = specs.get("regional_code", "?")

    pred   = price["predicted"]
    low    = price["low"]
    high   = price["high"]
    asking = price.get("asking")
    vd     = price.get("verdict")

    lines = [
        f"<b>{model} {st}GB</b> {color}",
        f"Battery: {bh}%  |  {origin}  |  {rc}",
        "",
        f"Prediksi harga wajar: <b>Rp {pred:,.0f}</b>",
        f"Range: Rp {low:,.0f} - Rp {high:,.0f}",
    ]
    if asking and vd:
        lines += [
            "",
            f"Harga listing: Rp {asking:,.0f}",
            f"Selisih: {vd['diff_pct']:+.1f}%",
            f"Verdict: <b>{vd['emoji']} {vd['label']}</b>",
        ]
    return "\n".join(lines)


def extract_price_from_text(text: str) -> Optional[int]:
    """Extract optional price override, e.g. 'Harga: 17600000'."""
    m = re.search(r"[Hh]arga\s*[:\-]?\s*([\d.,]+)", text)
    if m:
        try:
            return int(m.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            pass
    return None
