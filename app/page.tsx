"use client";

import { useState } from "react";

type Verdict = { label: string; emoji: string; diff_pct: number };
type Nego = { target_fair: number; target_min: number; save_fair: number; save_min: number };
type Resale = { fast: number; normal: number; premium: number; margin_fast?: number; margin_normal?: number; margin_premium?: number };
type PriceBlock = {
  predicted: number;
  low: number;
  high: number;
  asking: number | null;
  verdict: Verdict | null;
  nego: Nego | null;
  resale: Resale | null;
};
type Specs = {
  model: string;
  series: number;
  variant: string;
  storage_gb: number;
  color: string;
  battery_health: number;
  physical_condition: number;
  origin_type: string;
  regional_code: string;
  garansi_aktif: boolean;
  has_box: boolean;
  has_charger: boolean;
  has_manual: boolean;
};
type CheckResult = { specs: Specs; price: PriceBlock };

const fmt = (n: number) =>
  new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

const VERDICT_STYLE: Record<string, string> = {
  DEAL:      "bg-green-500/10 text-green-400 border-green-500/30",
  WAJAR:     "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  OVERPRICE: "bg-red-500/10 text-red-400 border-red-500/30",
};

export default function Home() {
  const [caption, setCaption]       = useState("");
  const [price, setPrice]           = useState("");
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState<CheckResult | null>(null);
  const [error, setError]           = useState<string | null>(null);

  async function handleCheck() {
    if (!caption.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caption: caption.trim(),
          listing_price: price ? parseInt(price.replace(/\D/g, "")) : null,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Gagal menganalisis caption.");
      }
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">Cek Harga iPhone</h1>
        <p className="text-sm text-[#737373] mt-1">Paste caption listing dari IG, langsung dapat verdict.</p>
      </div>

      {/* Input */}
      <div className="card space-y-3">
        <textarea
          className="input resize-none h-40 text-xs leading-relaxed"
          placeholder={"Paste caption dari Instagram di sini...\n\niPhone 16 Pro Max 256 GB Desert Titanium\nunit iBox Resmi Indonesia\n..."}
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
        />
        <input
          className="input"
          placeholder="Harga listing (opsional, contoh: 17600000)"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          inputMode="numeric"
        />
        <button className="btn-primary" onClick={handleCheck} disabled={loading || !caption.trim()}>
          {loading ? "Menganalisis..." : "Cek Harga →"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="card border-red-500/30 text-red-400 text-sm">{error}</div>
      )}

      {/* Result */}
      {result && <ResultCard result={result} />}
    </div>
  );
}

function ResultCard({ result }: { result: CheckResult }) {
  const { specs, price } = result;
  const vd = price.verdict;

  return (
    <div className="space-y-3">
      {/* Verdict banner */}
      {vd && (
        <div className={`card border text-center ${VERDICT_STYLE[vd.label]}`}>
          <div className="text-3xl mb-1">{vd.emoji}</div>
          <div className="text-xl font-bold">{vd.label}</div>
          <div className="text-sm mt-1 opacity-80">
            {vd.diff_pct > 0
              ? `${vd.diff_pct.toFixed(1)}% di atas harga wajar`
              : vd.diff_pct < 0
              ? `${Math.abs(vd.diff_pct).toFixed(1)}% di bawah harga wajar`
              : "Tepat di harga wajar"}
          </div>
        </div>
      )}

      {/* Price breakdown */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-sm text-[#a3a3a3] uppercase tracking-wider">Analisis Harga</h3>
        <div className="space-y-2">
          {price.asking && (
            <Row label="Harga listing" value={fmt(price.asking)} />
          )}
          <Row label="Prediksi harga wajar" value={fmt(price.predicted)} highlight />
          <div className="flex items-center justify-between text-xs text-[#737373]">
            <span>Range ±15%</span>
            <span>{fmt(price.low)} – {fmt(price.high)}</span>
          </div>
        </div>
      </div>

      {/* Nego */}
      {price.asking && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-sm text-[#a3a3a3] uppercase tracking-wider">Rekomendasi Nego</h3>
          {price.nego ? (
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-[#a3a3a3]">Target ideal</span>
                <span className="font-semibold text-white">{fmt(price.nego.target_fair)}<span className="text-green-400 text-xs ml-1">hemat {fmt(price.nego.save_fair)}</span></span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a3a3a3]">Target minimum</span>
                <span className="font-semibold text-[#d4d4d4]">{fmt(price.nego.target_min)}<span className="text-green-400 text-xs ml-1">hemat {fmt(price.nego.save_min)}</span></span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-[#737373]">
              {price.verdict?.label === "DEAL" ? "Harga sudah deal, tidak perlu nego." : "Harga sudah wajar, nego minor opsional."}
            </p>
          )}
        </div>
      )}

      {/* Resale */}
      {price.resale && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-sm text-[#a3a3a3] uppercase tracking-wider">Rekomendasi Harga Jual</h3>
          <div className="space-y-1.5 text-sm">
            {([
              ["Cepat laku (-7%)", price.resale.fast,    price.resale.margin_fast],
              ["Harga wajar",      price.resale.normal,  price.resale.margin_normal],
              ["Premium (+5%)",    price.resale.premium, price.resale.margin_premium],
            ] as [string, number, number | undefined][]).map(([label, val, margin]) => (
              <div key={label} className="flex justify-between items-baseline">
                <span className="text-[#a3a3a3]">{label}</span>
                <span className="text-right">
                  <span className="font-semibold text-[#d4d4d4]">{fmt(val)}</span>
                  {margin !== undefined && (
                    <span className={`text-xs ml-1.5 ${margin >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {margin >= 0 ? "+" : ""}{fmt(margin)}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
          {price.asking && <p className="text-xs text-[#525252] pt-1">Margin dihitung dari harga listing {fmt(price.asking)}</p>}
        </div>
      )}

      {/* Specs */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-sm text-[#a3a3a3] uppercase tracking-wider">Spesifikasi Terdeteksi</h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Spec label="Model"     value={specs.model} />
          <Spec label="Storage"   value={`${specs.storage_gb} GB`} />
          <Spec label="Warna"     value={specs.color || "—"} />
          <Spec label="Battery"   value={specs.battery_health ? `${specs.battery_health}%` : "—"} />
          <Spec label="Fisik"     value={specs.physical_condition ? `${specs.physical_condition}%` : "—"} />
          <Spec label="Origin"    value={specs.origin_type || "—"} />
          <Spec label="Regional"  value={specs.regional_code || "—"} />
          <Spec label="Garansi"   value={specs.garansi_aktif ? "Aktif" : "—"} />
        </div>
        <div className="flex gap-2 flex-wrap pt-1">
          {[
            ["Box",     specs.has_box],
            ["Charger", specs.has_charger],
            ["Manual",  specs.has_manual],
          ].map(([label, val]) => (
            <span
              key={label as string}
              className={`text-xs px-2 py-0.5 rounded-full border ${
                val ? "border-green-500/40 text-green-400" : "border-[#262626] text-[#525252]"
              }`}
            >
              {val ? "✓" : "✗"} {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-[#a3a3a3]">{label}</span>
      <span className={`text-sm font-semibold ${highlight ? "text-white" : "text-[#d4d4d4]"}`}>{value}</span>
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-[#737373]">{label}</div>
      <div className="font-medium text-sm truncate">{value}</div>
    </div>
  );
}
