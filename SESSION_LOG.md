# Session Log

---

## Session: 2026-03-13

### Summary
Major data expansion + parser improvement sprint, followed by a multi-step
production debugging session to get the new model live on Vercel.

---

### Data State
| Metric | Before | After |
|--------|--------|-------|
| Row count | 571 | 1,318 |
| Date range | ~Aug–Oct 2025 | Nov 2025 – Mar 2026 |
| Training rows (after filter) | 571 | 1,318 |

Filtered out during training:
- 3 dirty rows deleted from Supabase (CC28279, CC28837, CC28677 — price=1 or price=615K)
- iPhone 7 excluded (2 rows, no meaningful signal)
- Any price < 1,000,000 (placeholder guard)

Series seen in training data: 8, 11, 12, 13, 14, 15, 16, 17

---

### Model Metrics
Single GradientBoostingRegressor trained on all series/variants.

| Metric | Value |
|--------|-------|
| CV R² (10-fold) | 0.9845 ± 0.0081 |
| CV MAE | Rp 371,769 ± 23,774 |
| Train R² | 0.991 |
| Train MAE | Rp 301,735 |
| n_samples | 1,318 |
| Features | 20 |

CV MAE std improved significantly: ±73K (previous) → ±23K (current).
Model files: `model/saved_models/iphone_price_model.joblib` + `iphone_encoders.joblib` + `iphone_meta.json`

---

### Changes Made

#### 1. Data backfill (Nov 2025 → Mar 2026)
- Used Apify `apify/instagram-scraper` to backfill 589 new posts from @cherishcomapple
- `scraper/scraper.py`: `START_DATE` is now dynamic — queries `MAX(date_posted)` from Supabase
  at runtime, falls back to `2025-11-01` if table is empty
- `scraper/pipeline.py`: Added `--since YYYY-MM-DD` CLI argument

#### 2. Two new training features
`battery_replaced` and `has_aftermarket_part` added throughout the stack:
- `scraper/parser.py`: detection logic added
- `model/train.py`: added to `FEATURES` list and bool→int loop (defensive: `if c in df.columns else 0`)
- `model/predict.py`: added to `predict_price()` signature and row dict (both default `False`)
- `api/_shared.py`: added to `build_result()` call to `predict_range()`
- Supabase migration run manually:
  ```sql
  ALTER TABLE listings ADD COLUMN IF NOT EXISTS battery_replaced BOOLEAN DEFAULT FALSE;
  ALTER TABLE listings ADD COLUMN IF NOT EXISTS has_aftermarket_part BOOLEAN DEFAULT FALSE;
  ```
- 27 rows backfilled with `battery_replaced=True`, 54 with `has_aftermarket_part=True`

#### 3. Parser fixes (`scraper/parser.py`)
All fixes address real patterns found in @cherishcomapple captions:
- Added `_flag_negated()` helper: detects lines starting with ❌ emoji
- `has_box`, `has_manual`, `face_id_ok`: now guarded by `_flag_negated()`
- `has_charger`: rewritten as a line-by-line loop — skips ❌ lines and lines
  containing aftermarket brand names (Ugreen, Anker, Baseus, etc.)
- `lcd_original`: negative qualifiers (aftermarket, ganti LCD, non-original) + ❌ take precedence
- `battery_replaced`: detects "ganti baterai", "replace battery", "sudah/pernah ganti",
  and "aftermarket" on same line as "battery"
- `has_aftermarket_part`: catch-all for "aftermarket", "repair IC", "ganti IC", "refurb"

#### 4. Model training fixes (`model/train.py`)
- Fixed Supabase pagination: was capped at 1,000 rows; replaced with paginated loop
- `is_latest` feature: now dynamic (top-2 series in training data), stored in encoders dict
  so inference uses the same threshold without recomputing
- Price floor: explicit `>= 1_000_000` guard
- iPhone 7 exclusion: `df[df["series"] != 7]`

#### 5. Dead code removed
- `api/index.py` deleted — was a legacy Mangum-wrapped handler, not referenced in `vercel.json`

---

### Production Debugging (Vercel)

Four separate issues encountered and resolved after deploying the new model:

| # | Error | Root Cause | Fix |
|---|-------|------------|-----|
| 1 | `KeyError: battery_replaced` | New features added to `FEATURES` list but not to `predict_price()` row dict or `build_result()` | Added params with `False` defaults to both; made bool→int loop defensive |
| 2 | `dict \| None` syntax crash | `model/train.py` used Python 3.10+ union type syntax; Vercel defaults to Python 3.9 | Added `from __future__ import annotations` to `model/train.py` |
| 3 | Build failure: invalid `runtime` key | `"runtime": "python3.12"` is not valid in Vercel functions config | Removed; added `.python-version` file; `__future__` import already handles compat |
| 4 | `ValueError: MT19937 is not a known BitGenerator module` | `requirements.txt` pinned `numpy==1.26.4` but model was pickled with locally-installed `numpy==2.2.6` | Updated `requirements.txt`: numpy 1.26.4→2.2.6, pandas 2.2.2→3.0.1 |

Diagnosis method for issue 4: deployed a temporary `GET /api/debug` endpoint that ran
the full `parse_caption → build_result → predict_range` chain server-side and returned
the traceback as JSON. Removed after fix was confirmed.

**Final production state**: all endpoints live as of commit `83cf5f2`.

---

### Architectural Decisions

**Single model for all series/variants** (not per-series models)
The old `model/saved_models/series_N.joblib` files from a prior architecture are
still on disk but unused. The current architecture uses one GBR trained on all data
with engineered interaction features (`series_x_storage`, `is_pro`, `is_pro_max`,
`is_latest`) that carry the per-series signal. This simplified deployment and improved
accuracy on low-data series.

**`is_latest` threshold stored in encoders dict**
Rather than hardcoding `series >= 15`, the top-2 series threshold is computed at
training time and stored in `iphone_encoders.joblib` under key
`"latest_series_threshold"`. Inference reads it from there with a fallback of 15 for
old models. This means retraining automatically adjusts as new series appear.

**Verdict/nego/resale thresholds grounded in data**
All thresholds documented in `api/_shared.py` header:
- 75% of listings sit within ±5% of group mean
- p10 = -7% → fast-sell zone → resale `fast` tier at ×0.93
- p85 = +5% → premium zone → resale `premium` tier at ×1.05
- Nego only triggered when `diff_pct > 5%` (listing in top 15%)
- Confidence interval: ±15% (covers ~1σ of within-group price std of 7–13%)

**Split Vercel handlers** (`api/check.py`, `api/predict.py`, etc.)
Each endpoint is its own file with its own `app = FastAPI()`. No Mangum adapter.
Vercel auto-detects `.py` files and serves the `app` ASGI object.

---

### Remaining Items (Not Done)

- **Transaction / purchase tracking**: no table or UI for recording actual buys
- **Frontend UI**: no web UI exists; the app is API-only + Telegram bot
- **Narrower confidence interval**: ±15% is wide; could be per-series-variant once
  more data accumulates (need ~50+ samples per group for reliable std estimates)
- **Old series_N.joblib files**: still in `model/saved_models/`, unused dead weight —
  could be deleted in a cleanup commit
- **`api/predict.py` missing new fields**: `battery_replaced` and `has_aftermarket_part`
  are not exposed in the `PredictRequest` schema (they have `False` defaults so it works,
  but callers can't pass them explicitly via the `/api/predict` endpoint)

---

### Environment Pins (as of this session)
```
numpy==2.2.6
pandas==3.0.1
scikit-learn==1.4.2
joblib==1.4.2
fastapi==0.111.0
supabase==2.4.6
python-dotenv==1.0.1
httpx==0.27.0
```
Python: 3.12 (Vercel, via `.python-version`); local Windows dev uses same.

> **Note for future sessions**: always retrain locally and commit the `.joblib` files.
> The model is checked into git — Vercel has no training environment. If you upgrade
> numpy or sklearn, retrain immediately before pushing, or the pickle will be
> incompatible with whatever version requirements.txt installs.
