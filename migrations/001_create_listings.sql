-- Migration: 001_create_listings.sql
-- Creates the listings table for iPhone pricing data from @cherishcomapple

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS listings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date_posted             DATE,
    series                  INT,
    variant                 TEXT,               -- Regular, Pro, Pro Max, XR, Plus, Mini, etc.
    model                   TEXT,               -- Full model string e.g. "iPhone 16 Pro Max"
    storage_gb              INT,
    color                   TEXT,
    battery_health          INT,                -- 0-100
    physical_condition      INT,                -- 0-100 (from "Fisik 95%")
    origin_type             TEXT,               -- iBox, TAM, Digimap, Inter, Urban, Blibli Resmi, etc.
    regional_code           TEXT,               -- PA/A, ID/A, ZP/A, J/A, SA/A
    garansi_aktif           BOOLEAN,
    garansi_expired_fullset DATE,               -- nullable; date garansi expires if fullset
    has_box                 BOOLEAN,
    has_charger             BOOLEAN,
    has_manual              BOOLEAN,
    face_id_ok              BOOLEAN,
    lcd_original            BOOLEAN,
    battery_replaced        BOOLEAN DEFAULT FALSE,
    has_aftermarket_part    BOOLEAN DEFAULT FALSE,
    price_idr               BIGINT,
    source_code             TEXT UNIQUE,        -- Kode Barang e.g. CC28865
    notes                   TEXT,               -- nullable; any extra info
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Index for common query patterns
CREATE INDEX IF NOT EXISTS idx_listings_series        ON listings (series);
CREATE INDEX IF NOT EXISTS idx_listings_model         ON listings (model);
CREATE INDEX IF NOT EXISTS idx_listings_date_posted   ON listings (date_posted DESC);
CREATE INDEX IF NOT EXISTS idx_listings_price_idr     ON listings (price_idr);
CREATE INDEX IF NOT EXISTS idx_listings_source_code   ON listings (source_code);
