"""
train.py — Single GBR model for iPhone resale price prediction.

One model trained on all series/variants. Engineered interaction features
(series_x_storage, is_pro_max, etc.) carry most of the predictive signal.
Designed to retrain cleanly as more scraped data accumulates over time.

Usage
-----
    python model/train.py           # train on all data
    python model/train.py --eval    # show detailed evaluation only, no save
"""

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from supabase import create_client

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

MODEL_DIR   = Path(__file__).parent / "saved_models"
MODEL_PATH  = MODEL_DIR / "iphone_price_model.joblib"
ENC_PATH    = MODEL_DIR / "iphone_encoders.joblib"
META_PATH   = MODEL_DIR / "iphone_meta.json"

MIN_PRICE = 1_000_000   # filter placeholder / corrupt prices

# Categorical features to label-encode
CATEGORICAL = ["variant", "origin_type", "regional_code"]

# Final feature order (must match predict.py)
FEATURES = [
    # Raw numerics
    "series_num",
    "storage_gb",
    "battery_health",
    "physical_condition",
    "garansi_aktif",
    "garansi_days_remaining",
    "has_box",
    "has_charger",
    "has_manual",
    "face_id_ok",
    "lcd_original",
    # Encoded categoricals
    "variant_enc",
    "origin_enc",
    "regional_enc",
    # Engineered interactions
    "is_pro",
    "is_pro_max",
    "is_latest",
    "series_x_storage",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_from_supabase() -> pd.DataFrame:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    client = create_client(url, key)
    return pd.DataFrame(client.table("listings").select("*").execute().data)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame, encoders: dict | None = None, fit: bool = True) -> tuple[pd.DataFrame, dict]:
    """
    Build the full feature matrix.

    Parameters
    ----------
    df       : Raw listings DataFrame.
    encoders : Existing encoders dict (for inference). None = create new.
    fit      : If True, fit new LabelEncoders (training). If False, transform only.

    Returns
    -------
    df_feat  : DataFrame with exactly the columns in FEATURES.
    encoders : Dict of fitted LabelEncoders + metadata.
    """
    from datetime import date
    today = date.today()

    df = df.copy()

    # ---- numeric series ----
    df["series_num"] = pd.to_numeric(df["series"], errors="coerce").fillna(0).astype(float)

    # ---- storage ----
    df["storage_gb"] = pd.to_numeric(df["storage_gb"], errors="coerce").fillna(128).astype(float)

    # ---- battery / condition ----
    df["battery_health"]     = pd.to_numeric(df["battery_health"],     errors="coerce").fillna(85).astype(float)
    df["physical_condition"] = pd.to_numeric(df["physical_condition"], errors="coerce").fillna(90).astype(float)

    # ---- booleans → int ----
    for c in ["garansi_aktif", "has_box", "has_charger", "has_manual", "face_id_ok", "lcd_original"]:
        df[c] = df[c].fillna(False).astype(int)

    # ---- warranty days remaining ----
    def _days(row):
        val = row.get("garansi_expired_fullset")
        if not val:
            return 0
        try:
            return max(0, (date.fromisoformat(str(val)) - today).days)
        except ValueError:
            return 0

    df["garansi_days_remaining"] = df.apply(_days, axis=1).astype(float)

    # ---- label encode categoricals ----
    if encoders is None:
        encoders = {}

    for col, key in [("variant", "variant_enc"), ("origin_type", "origin_enc"), ("regional_code", "regional_enc")]:
        df[col] = df[col].fillna("Unknown").astype(str)
        if fit:
            le = LabelEncoder()
            df[key] = le.fit_transform(df[col])
            encoders[key] = le
        else:
            le = encoders[key]
            # unseen labels → "Unknown" (or 0 if Unknown not in classes)
            known = set(le.classes_)
            df[col] = df[col].apply(lambda x: x if x in known else ("Unknown" if "Unknown" in known else le.classes_[0]))
            df[key] = le.transform(df[col])

    # ---- interaction / binary features ----
    variant_col = df["variant"].str.strip()
    df["is_pro_max"] = (variant_col == "Pro Max").astype(int)
    df["is_pro"]     = (variant_col.isin(["Pro", "Pro Max"])).astype(int)
    df["is_latest"]  = (df["series_num"] >= 15).astype(int)

    # The single most powerful feature: captures price tier naturally
    df["series_x_storage"] = df["series_num"] * df["storage_gb"]

    # ---- ensure all feature columns exist ----
    for col in FEATURES:
        if col not in df.columns:
            df[col] = 0.0

    return df[FEATURES], encoders


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

def train(eval_only: bool = False) -> None:
    print("[train] Loading data from Supabase ...")
    df_raw = _load_from_supabase()
    print(f"[train] {len(df_raw)} total rows loaded.")

    # Clean: require series, storage, price; drop placeholder prices
    df = df_raw.dropna(subset=["series", "storage_gb", "price_idr"]).copy()
    df["price_idr"] = pd.to_numeric(df["price_idr"], errors="coerce")
    df = df[df["price_idr"] >= MIN_PRICE]
    print(f"[train] {len(df)} clean rows after filtering (dropped {len(df_raw) - len(df)}).")

    X, encoders = engineer_features(df, fit=True)
    y = df["price_idr"].values

    # ---- Cross-validation (honest estimate) ----
    # n_splits scales with data: more data → more folds → better estimate
    n_splits = min(10, max(5, len(df) // 30))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    model = _make_model(len(df))

    cv_r2  = cross_val_score(model, X, y, cv=kf, scoring="r2")
    cv_mae = cross_val_score(model, X, y, cv=kf, scoring="neg_mean_absolute_error")

    print(f"\n[train] {n_splits}-fold Cross-Validation:")
    print(f"  R²  = {cv_r2.mean():.4f}  +/- {cv_r2.std():.4f}")
    print(f"  MAE = Rp {-cv_mae.mean():>12,.0f}  +/- Rp {cv_mae.std():,.0f}")
    print(f"  Avg error = {(-cv_mae.mean() / y.mean() * 100):.1f}% of mean price")

    if eval_only:
        print("\n[train] --eval mode: model not saved.")
        return

    # ---- Fit on full data ----
    model.fit(X, y)

    # In-sample metrics (sanity check)
    y_pred_train = model.predict(X)
    train_r2  = r2_score(y, y_pred_train)
    train_mae = mean_absolute_error(y, y_pred_train)
    print(f"\n[train] In-sample (train set):")
    print(f"  R²  = {train_r2:.4f}")
    print(f"  MAE = Rp {train_mae:,.0f}")

    # Feature importance
    fi = sorted(zip(FEATURES, model.feature_importances_), key=lambda x: x[1], reverse=True)
    print("\n[train] Feature importances (top 10):")
    for feat, imp in fi[:10]:
        bar = "#" * int(imp * 300)
        print(f"  {feat:<22} {imp:.4f}  {bar}")

    # ---- Save ----
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model,    MODEL_PATH)
    joblib.dump(encoders, ENC_PATH)

    meta = {
        "n_samples":      int(len(df)),
        "features":       FEATURES,
        "cv_r2_mean":     round(float(cv_r2.mean()),  4),
        "cv_r2_std":      round(float(cv_r2.std()),   4),
        "cv_mae_mean":    round(float(-cv_mae.mean()), 0),
        "cv_mae_std":     round(float(cv_mae.std()),   0),
        "train_r2":       round(float(train_r2),       4),
        "train_mae":      round(float(train_mae),      0),
        "gbr_params":     model.get_params(),
        "series_seen":    sorted(pd.to_numeric(df["series"], errors="coerce").dropna().astype(int).unique().tolist()),
    }
    with META_PATH.open("w") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\n[train] Saved -> {MODEL_PATH.name}")
    print(f"[train] n={len(df)}  CV R²={cv_r2.mean():.3f}  CV MAE=Rp {-cv_mae.mean():,.0f}")


def _make_model(n_samples: int) -> GradientBoostingRegressor:
    """
    GBR params that scale reasonably as data grows.

    Current (~300 rows): conservative to avoid overfit.
    Future (1000+ rows): same params still valid; n_estimators can be
    bumped manually once data is larger.
    """
    return GradientBoostingRegressor(
        n_estimators=200,       # enough signal; increase to 300+ when n > 800
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=5,     # prevents overfit on small groups
        subsample=0.8,
        random_state=42,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train iPhone price model")
    parser.add_argument("--eval", action="store_true", help="Cross-validate only, do not save model")
    args = parser.parse_args()
    train(eval_only=args.eval)
