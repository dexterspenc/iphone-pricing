"""
parser.py — Regex parser for @cherishcomapple Instagram captions.

Extracts structured listing data from the standardised caption format used by
the account. All fields map 1-to-1 with the `listings` Supabase table.
"""

import re
from datetime import datetime, date
from typing import Optional


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

MONTH_MAP: dict[str, int] = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

# iPhone variant keywords (order matters — longer/more-specific first)
VARIANT_PATTERNS: list[tuple[str, str]] = [
    (r"pro\s*max",  "Pro Max"),
    (r"\bpro\b",    "Pro"),
    (r"\bplus\b",   "Plus"),
    (r"\bmini\b",   "Mini"),
    (r"\bxr\b",     "XR"),
    (r"xs\s*max",   "XS Max"),
    (r"\bxs\b",     "XS"),
    (r"\bse\b",     "SE"),
]

# Origin / distributor keywords
ORIGIN_PATTERNS: list[tuple[str, str]] = [
    (r"ibox",                         "iBox"),
    (r"tam\b",                        "TAM"),
    (r"digimap",                      "Digimap"),
    (r"blibli\s*resmi",               "Blibli Resmi"),
    (r"resmi\s*indonesia",            "Resmi Indonesia"),
    (r"\binter(national)?\b",        "Inter"),
    (r"urban\s*republic",             "Urban Republic"),
    (r"urban",                        "Urban"),
    (r"second",                       "Second"),
]


# ---------------------------------------------------------------------------
# Helper parsers
# ---------------------------------------------------------------------------

def _parse_indonesian_date(text: str) -> Optional[date]:
    """Parse 'DD MonthName YYYY' Indonesian date strings."""
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(MONTH_MAP.keys()) + r")\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    return date(year, MONTH_MAP[month_str], day)


def _flag(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_caption(caption: str, date_posted: Optional[date] = None) -> Optional[dict]:
    """
    Parse a @cherishcomapple caption and return a dict matching the
    `listings` table schema, or None if the caption cannot be parsed.

    Parameters
    ----------
    caption     : Raw Instagram caption string.
    date_posted : Date the post was published (from Instaloader metadata).
    """
    if not caption or not isinstance(caption, str):
        return None

    text = caption.strip()
    lower = text.lower()

    # ------------------------------------------------------------------
    # 1. Series & variant
    # ------------------------------------------------------------------
    series_match = re.search(r"iphone\s+(\d{1,2})", lower)
    if not series_match:
        return None  # not an iPhone listing
    series = int(series_match.group(1))

    variant = "Regular"
    for pattern, label in VARIANT_PATTERNS:
        if re.search(pattern, lower):
            variant = label
            break

    # Build canonical model string
    model = f"iPhone {series}" + ("" if variant == "Regular" else f" {variant}")

    # ------------------------------------------------------------------
    # 2. Storage  (handles both GB and TB — 1 TB stored as 1000 GB)
    # ------------------------------------------------------------------
    storage_match = re.search(r"(\d+)\s*gb", lower)
    if storage_match:
        storage_gb = int(storage_match.group(1))
    else:
        tb_match = re.search(r"(\d+)\s*tb", lower)
        storage_gb = int(tb_match.group(1)) * 1000 if tb_match else None

    # ------------------------------------------------------------------
    # 3. Color — everything after the storage size (GB or TB) on the
    #    iPhone model line, up to the next newline
    # ------------------------------------------------------------------
    color: Optional[str] = None
    color_match = re.search(
        r"iphone\s+\S.*?\d+\s*(?:gb|tb)\s+(.+?)(?:\n|$)", text, re.IGNORECASE
    )
    if color_match:
        color = color_match.group(1).strip()

    # ------------------------------------------------------------------
    # 4. Battery health  ("Battery Health 90%" / "BH 90%" / "bh: 90")
    # ------------------------------------------------------------------
    battery_match = re.search(
        r"(?:battery\s*health|bh)\s*[:\-]?\s*(\d{1,3})\s*%?",
        lower,
    )
    battery_health = int(battery_match.group(1)) if battery_match else None

    # ------------------------------------------------------------------
    # 5. Physical condition  ("Fisik 95%" / "kondisi fisik 95")
    # ------------------------------------------------------------------
    phys_match = re.search(r"fisik\s*[:\-]?\s*(\d{1,3})\s*%?", lower)
    physical_condition = int(phys_match.group(1)) if phys_match else None

    # ------------------------------------------------------------------
    # 5b. Brand New in Box (BNIB) — sealed units have no Fisik/Battery
    #     section; default both to 100 when none were found
    # ------------------------------------------------------------------
    is_bnib = _flag(r"brand\s*new|masih\s*segel|baru\s*segel|new\s*segel|\bbnib\b", text)
    if is_bnib:
        if battery_health is None:
            battery_health = 100
        if physical_condition is None:
            physical_condition = 100

    # ------------------------------------------------------------------
    # 6. Origin type
    # ------------------------------------------------------------------
    origin_type: Optional[str] = None
    for pattern, label in ORIGIN_PATTERNS:
        if re.search(pattern, lower):
            origin_type = label
            break

    # ------------------------------------------------------------------
    # 7. Regional code  (SA/A  ID/A  ZP/A  PA/A  J/A  LL/A …)
    # ------------------------------------------------------------------
    regional_match = re.search(
        r"\b([A-Z]{1,3}/A)\b",
        text,  # use original case to preserve capitalisation
    )
    regional_code = regional_match.group(1) if regional_match else None

    # ------------------------------------------------------------------
    # 8. Garansi (warranty)
    # ------------------------------------------------------------------
    garansi_aktif = _flag(r"garansi\s+aktif", text)

    garansi_expired_fullset: Optional[date] = None
    if garansi_aktif:
        # Try to extract the expiry date that follows "Garansi Aktif"
        garansi_line_match = re.search(r"garansi\s+aktif\s+(.+?)(?:\n|$)", text, re.IGNORECASE)
        if garansi_line_match:
            garansi_expired_fullset = _parse_indonesian_date(garansi_line_match.group(1))

    # ------------------------------------------------------------------
    # 9. Accessories / accessories flags
    # ------------------------------------------------------------------
    has_box     = _flag(r"\bbox\b",                          lower)
    has_charger = _flag(r"charger",                          lower)
    has_manual  = _flag(r"manual\s*(book)?",                 lower)

    # ------------------------------------------------------------------
    # 10. Device condition flags
    # ------------------------------------------------------------------
    face_id_ok   = _flag(r"face\s*id\s*(oke|ok|lancar|normal|work)", lower)
    lcd_original = _flag(r"lcd\s*original",                          lower)

    # ------------------------------------------------------------------
    # 11. Price  (IDR 17.600.000 / Rp 17.600.000 / 17600000)
    # ------------------------------------------------------------------
    price_idr: Optional[int] = None
    price_match = re.search(
        r"(?:idr|rp\.?)\s*([\d.,]+)",
        lower,
    )
    if price_match:
        raw_price = price_match.group(1).replace(".", "").replace(",", "")
        price_idr = int(raw_price)

    # ------------------------------------------------------------------
    # 12. Source code  (Kode Barang: CC28865)
    # ------------------------------------------------------------------
    source_match = re.search(r"kode\s*barang\s*[:\-]?\s*(\S+)", text, re.IGNORECASE)
    source_code = source_match.group(1).strip() if source_match else None

    # ------------------------------------------------------------------
    # 13. Notes — capture seller phone, location as misc notes
    # ------------------------------------------------------------------
    notes_parts = []
    wa_match  = re.search(r"wa\s*seller\s*[:\-]?\s*(\S+)", text, re.IGNORECASE)
    loc_match = re.search(r"lokasi\s*[:\-]?\s*(.+?)(?:\n|$)",  text, re.IGNORECASE)
    if wa_match:
        notes_parts.append(f"WA: {wa_match.group(1)}")
    if loc_match:
        notes_parts.append(f"Lokasi: {loc_match.group(1).strip()}")
    notes = "; ".join(notes_parts) if notes_parts else None

    # ------------------------------------------------------------------
    # Assemble result
    # ------------------------------------------------------------------
    return {
        "date_posted":             date_posted.isoformat() if date_posted else None,
        "series":                  series,
        "variant":                 variant,
        "model":                   model,
        "storage_gb":              storage_gb,
        "color":                   color,
        "battery_health":          battery_health,
        "physical_condition":      physical_condition,
        "origin_type":             origin_type,
        "regional_code":           regional_code,
        "garansi_aktif":           garansi_aktif,
        "garansi_expired_fullset": garansi_expired_fullset.isoformat() if garansi_expired_fullset else None,
        "has_box":                 has_box,
        "has_charger":             has_charger,
        "has_manual":              has_manual,
        "face_id_ok":              face_id_ok,
        "lcd_original":            lcd_original,
        "price_idr":               price_idr,
        "source_code":             source_code,
        "notes":                   notes,
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE = """iPhone 16 Pro Max 256 GB Desert Titanium
unit Blibli Resmi Indonesia
Garansi Aktif 8 Juli 2026
Fullset siap pakai
Kondisi
Fisik 95%, pemakaian masih bagus
Spesifikasi & Fitur :
Face ID Lancar
True tone
LCD Original
Kamera Jernih
Kamera Silent
ICloud bersih
No dead pixel
Wifi normal
Battery Health 98%
Model Regional SA/A
Resmi Indonesia
Mesin Normal no minus
Kelengkapan :
Unit
Box
Charger cable
Manual book
Harga & Info Seller
IDR 17.600.000
WA Seller: 082210042951
Lokasi: Jakarta Pusat
Bisa Rekber via Cherishcom
Kode Barang: CC28865"""

    import json
    result = parse_caption(SAMPLE, date_posted=date(2024, 6, 1))
    print(json.dumps(result, indent=2, default=str))
