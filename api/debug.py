"""api/debug.py — Temporary runtime diagnostic. DELETE after fix."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/debug")
def debug():
    results = {"python_version": sys.version}

    try:
        from scraper.parser import parse_caption
        from _shared import build_result

        caption = (
            "iPhone 16 Pro Max 256 GB Desert Titanium\n"
            "iBox\n"
            "Fisik 95%\n"
            "Battery Health 98%\n"
            "Face ID OK\n"
            "LCD Original\n"
            "Box\n"
            "Charger cable\n"
            "SA/A\n"
            "IDR 17.600.000\n"
            "Kode Barang: DEBUGTEST1"
        )

        parsed = parse_caption(caption)
        results["parsed_series"]  = parsed.get("series")
        results["parsed_variant"] = parsed.get("variant")

        result = build_result(parsed, 17_600_000)
        results["predicted"] = result["price"]["predicted"]
        results["verdict"]   = result["price"]["verdict"]["label"]
        results["status"]    = "OK"

    except Exception as e:
        results["status"]    = "ERROR"
        results["error"]     = f"{type(e).__name__}: {e}"
        results["traceback"] = traceback.format_exc()

    return results
