"""api/bot.py — POST /api/bot (Telegram webhook)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from _shared import (
    build_result, tg_send, format_tg_reply,
    extract_price_from_text, parse_caption,
)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[dict] = None


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
        tg_send(chat_id, (
            "Halo! 👋\n\n"
            "Paste caption listing iPhone dari IG langsung ke sini, "
            "nanti saya analisis apakah harganya <b>DEAL / WAJAR / OVERPRICE</b>.\n\n"
            "Kalau mau cantumin harga listing, tambahkan baris:\n"
            "<code>Harga: 17600000</code>\ndi awal atau akhir caption."
        ))
        return {"ok": True}

    if text.startswith("/help"):
        tg_send(chat_id, (
            "<b>Cara pakai:</b>\n"
            "1. Copy caption postingan IG @cherishcomapple\n"
            "2. Paste langsung ke chat ini\n"
            "3. Dapat verdict otomatis!\n\n"
            "Optional: tambahkan <code>Harga: 17600000</code> "
            "di caption untuk perbandingan harga listing."
        ))
        return {"ok": True}

    listing_price = extract_price_from_text(text)

    try:
        parsed = parse_caption(text)
        if not parsed or not parsed.get("series"):
            tg_send(chat_id, "Hmm, caption ini tidak dikenali sebagai listing iPhone. Coba paste ulang caption lengkapnya ya.")
            return {"ok": True}

        result = build_result(parsed, listing_price or parsed.get("price_idr"))
        tg_send(chat_id, format_tg_reply(result))

    except Exception as e:
        tg_send(chat_id, f"Ada error saat analisis: {str(e)[:100]}")

    return {"ok": True}
