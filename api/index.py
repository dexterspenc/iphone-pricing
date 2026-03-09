"""
api/index.py — FastAPI backend, deployed as Vercel serverless function.

Endpoints:
  POST /api/check       — parse caption + predict + verdict
  POST /api/predict     — predict from structured input
  GET  /api/listings    — recent listings from Supabase
  POST /api/bot         — Telegram webhook handler
"""

import os
import sys
import json
import httpx
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel
from dotenv import load_dotenv

# ── path setup so we can import model/ and scraper/ ──────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scraper.parser import parse_caption
from model.predict import predict_price, predict_range

# ── app ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="iPhone Pricing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── schemas ───────────────────────────────────────────────────────────────────

class CheckRequest(BaseModel):
    caption: str
    listing_price: Optional[int] = None

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
    listing_price: Optional[int] = None

class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[dict] = None

# ── helpers ───────────────────────────────────────────────────────────────────

def _verdict(listing_price: int, low: float, high: float, predicted: float) -> dict:
    if listing_price <= low:
        label, emoji = "DEAL", "🔥"
    elif listing_price <= high:
        label, emoji = "WAJAR", "👍"
    else:
        label, emoji = "OVERPRICE", "❌"
    diff_pct = (listing_price - predicted) / predicted * 100
    return {"label": label, "emoji": emoji, "diff_pct": round(diff_pct, 1)}


def _build_result(parsed: dict, listing_price: Optional[int]) -> dict:
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
        price_block["verdict"] = _verdict(
            listing_price, result["low_idr"], result["high_idr"], result["predicted_idr"]
        )

    return {"specs": parsed, "price": price_block}

# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api")
def root():
    return {"status": "ok", "service": "iphone-pricing-api"}


@app.post("/api/check")
def check(req: CheckRequest):
    parsed = parse_caption(req.caption)
    if not parsed or not parsed.get("series"):
        raise HTTPException(status_code=422, detail="Gagal parse caption — bukan listing iPhone yang dikenali.")
    return _build_result(parsed, req.listing_price or parsed.get("price_idr"))


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
    )
    if req.listing_price:
        result["verdict"] = _verdict(
            req.listing_price, result["low_idr"], result["high_idr"], result["predicted_idr"]
        )
    return result


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


# ── Telegram bot ──────────────────────────────────────────────────────────────

def _tg_send(chat_id: int, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )


def _format_tg_reply(result: dict) -> str:
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


@app.post("/api/bot")
def telegram_webhook(update: TelegramUpdate):
    msg = update.message
    if not msg:
        return {"ok": True}

    chat_id = msg.get("chat", {}).get("id")
    text    = msg.get("text", "").strip()

    if not chat_id or not text:
        return {"ok": True}

    if text.startswith("/start"):
        _tg_send(chat_id, (
            "Halo! 👋\n\n"
            "Paste caption listing iPhone dari IG langsung ke sini, "
            "nanti saya analisis apakah harganya <b>DEAL / WAJAR / OVERPRICE</b>.\n\n"
            "Kalau mau cantumin harga listing, tambahkan baris:\n"
            "<code>Harga: 17600000</code>\ndi awal atau akhir caption."
        ))
        return {"ok": True}

    if text.startswith("/help"):
        _tg_send(chat_id, (
            "<b>Cara pakai:</b>\n"
            "1. Copy caption postingan IG @cherishcomapple\n"
            "2. Paste langsung ke chat ini\n"
            "3. Dapat verdict otomatis!\n\n"
            "Optional: tambahkan <code>Harga: 17600000</code> "
            "di caption untuk perbandingan harga listing."
        ))
        return {"ok": True}

    # Extract optional price override from message (e.g. "Harga: 17600000")
    import re
    listing_price = None
    price_override = re.search(r"[Hh]arga\s*[:\-]?\s*([\d.,]+)", text)
    if price_override:
        try:
            listing_price = int(price_override.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            pass

    try:
        parsed = parse_caption(text)
        if not parsed or not parsed.get("series"):
            _tg_send(chat_id, "Hmm, caption ini tidak dikenali sebagai listing iPhone. Coba paste ulang caption lengkapnya ya.")
            return {"ok": True}

        result = _build_result(parsed, listing_price or parsed.get("price_idr"))
        reply  = _format_tg_reply(result)
        _tg_send(chat_id, reply)

    except Exception as e:
        _tg_send(chat_id, f"Ada error saat analisis: {str(e)[:100]}")

    return {"ok": True}


# ── Vercel handler ────────────────────────────────────────────────────────────
handler = Mangum(app, lifespan="off")
