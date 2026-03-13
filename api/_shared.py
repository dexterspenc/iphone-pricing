"""
api/_shared.py — Shared helpers for all API functions.
Underscore prefix = not treated as a Vercel serverless function.

Nego & resale thresholds grounded in data (573 listings, @cherishcomapple):
  - 75% of listings sit within ±5% of group mean
  - p10 = -7%  → fast-sell zone
  - p85 = +5%  → premium zone
  - Nego only meaningful when diff_pct > 5% (listing in top 15%)
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


# ── nego recommendation ───────────────────────────────────────────────────────

def make_nego(asking: int, predicted: float, high: float, diff_pct: float) -> Optional[dict]:
    """
    Only recommend nego when asking > predicted + 5% (top 15% of market).
    - target_fair  : bring to predicted (median market price)
    - target_min   : bring to high (top of WAJAR range, minimum acceptable)
    """
    if diff_pct <= 5:
        return None  # already fair or deal, no nego needed

    target_fair = round(predicted, -3)
    target_min  = round(high, -3)

    return {
        "target_fair": target_fair,
        "target_min":  target_min,
        "save_fair":   round(asking - target_fair, -3),
        "save_min":    round(asking - target_min, -3),
    }


# ── resale recommendation ─────────────────────────────────────────────────────

def make_resale(predicted: float, asking: Optional[int]) -> dict:
    """
    Three resale tiers grounded in data distribution:
    - fast    : predicted × 0.93  (p10 = -7%, undercuts 90% of market → quick sale)
    - normal  : predicted          (p50 = median, fair market)
    - premium : predicted × 1.05  (p85 = +5%, top 15% → needs patient buyer)

    If asking price known, also show estimated margin at each tier.
    """
    fast    = round(predicted * 0.93, -3)
    normal  = round(predicted,        -3)
    premium = round(predicted * 1.05, -3)

    result: dict = {"fast": fast, "normal": normal, "premium": premium}

    if asking:
        result["margin_fast"]    = round(fast    - asking, -3)
        result["margin_normal"]  = round(normal  - asking, -3)
        result["margin_premium"] = round(premium - asking, -3)

    return result


# ── build full result ─────────────────────────────────────────────────────────

def build_result(parsed: dict, listing_price: Optional[int]) -> dict:
    result = predict_range(
        series=parsed["series"],
        variant=parsed.get("variant", "Regular"),
        storage_gb=parsed.get("storage_gb") or 128,
        battery_health=parsed.get("battery_health") or 90,
        physical_condition=parsed.get("physical_condition") or 90,
        origin_type=parsed.get("origin_type") or "iBox",
        regional_code=parsed.get("regional_code") or "PA/A",
        garansi_aktif=parsed.get("garansi_aktif", False),
        garansi_expired_fullset=parsed.get("garansi_expired_fullset"),
        has_box=parsed.get("has_box", True),
        has_charger=parsed.get("has_charger", True),
        has_manual=parsed.get("has_manual", True),
        face_id_ok=parsed.get("face_id_ok", True),
        lcd_original=parsed.get("lcd_original", True),
        battery_replaced=parsed.get("battery_replaced", False),
        has_aftermarket_part=parsed.get("has_aftermarket_part", False),
    )

    predicted = result["predicted_idr"]
    low       = result["low_idr"]
    high      = result["high_idr"]

    price_block: dict = {
        "predicted": predicted,
        "low":       low,
        "high":      high,
        "asking":    listing_price,
        "verdict":   None,
        "nego":      None,
        "resale":    make_resale(predicted, listing_price),
    }

    if listing_price:
        vd = make_verdict(listing_price, low, high, predicted)
        price_block["verdict"] = vd
        price_block["nego"]    = make_nego(listing_price, predicted, high, vd["diff_pct"])

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


def _fmt(n: int) -> str:
    return f"Rp {n:,.0f}"

def _margin_label(m: int) -> str:
    if m > 0:
        return f"<b>+{_fmt(m)}</b> untung"
    elif m < 0:
        return f"{_fmt(m)} rugi"
    return "impas"


def format_tg_reply(result: dict) -> str:
    specs = result["specs"]
    price = result["price"]

    model  = specs.get("model", "iPhone")
    st     = specs.get("storage_gb", "?")
    color  = specs.get("color", "") or ""
    bh     = specs.get("battery_health", "?")
    origin = specs.get("origin_type", "?") or "?"
    rc     = specs.get("regional_code", "?") or "?"

    pred   = price["predicted"]
    low    = price["low"]
    high   = price["high"]
    asking = price.get("asking")
    vd     = price.get("verdict")
    nego   = price.get("nego")
    resale = price.get("resale", {})

    lines = [
        f"<b>{model} {st}GB</b>{' ' + color if color else ''}",
        f"BH: {bh}%  |  {origin}  |  {rc}",
        "",
        "💰 <b>Analisis Harga</b>",
        f"Prediksi wajar: <b>{_fmt(pred)}</b>",
        f"Range: {_fmt(low)} – {_fmt(high)}",
    ]

    if asking and vd:
        diff = vd['diff_pct']
        if vd['label'] == "DEAL":
            summary = f"{abs(diff):.1f}% lebih murah dari harga pasar — harga bagus"
        elif vd['label'] == "OVERPRICE":
            summary = f"{diff:.1f}% di atas harga pasar — terlalu mahal"
        elif diff > 0:
            summary = f"{diff:.1f}% di atas prediksi — masih rentang normal"
        elif diff < 0:
            summary = f"{abs(diff):.1f}% di bawah prediksi — harga oke"
        else:
            summary = "Tepat di harga pasar"

        lines += [
            "",
            f"Harga listing: {_fmt(asking)}",
            f"Verdict: <b>{vd['emoji']} {vd['label']}</b>",
            f"<i>{summary}</i>",
        ]

    # Nego block
    if nego:
        lines += [
            "",
            "🤝 <b>Nego</b>",
            "Listing ini kemahalan. Coba tawar ke:",
            f"  Ideal (harga pasar) : {_fmt(nego['target_fair'])} — hemat {_fmt(nego['save_fair'])}",
            f"  Minimum (batas wajar): {_fmt(nego['target_min'])} — hemat {_fmt(nego['save_min'])}",
        ]
    elif asking and vd:
        if vd['label'] == "DEAL":
            nego_note = "Harga sudah bagus banget, tidak perlu nego."
        else:
            nego_note = "Harga masuk akal. Nego kecil boleh dicoba, tapi seller belum tentu mau."
        lines += ["", f"🤝 {nego_note}"]

    # Resale block
    if resale:
        if asking:
            lines += ["", f"📈 <b>Estimasi Harga Jual</b> (jika beli di {_fmt(asking)}):"]
            lines.append(f"  BEP (balik modal) : {_fmt(asking)}")
        else:
            lines += ["", "📈 <b>Estimasi Harga Jual</b>"]
        tiers = [
            ("Cepat laku",  resale["fast"],    resale.get("margin_fast")),
            ("Harga pasar", resale["normal"],  resale.get("margin_normal")),
            ("Premium",     resale["premium"], resale.get("margin_premium")),
        ]
        for label, price_val, margin in tiers:
            margin_str = f" → {_margin_label(margin)}" if margin is not None else ""
            lines.append(f"  {label}: {_fmt(price_val)}{margin_str}")

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
