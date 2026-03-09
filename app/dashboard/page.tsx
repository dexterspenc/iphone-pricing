"use client";

import { useEffect, useState } from "react";

type Listing = {
  id: string;
  date_posted: string;
  series: number;
  variant: string;
  model: string;
  storage_gb: number;
  color: string;
  battery_health: number;
  origin_type: string;
  regional_code: string;
  price_idr: number;
  source_code: string;
};

const fmt = (n: number) =>
  new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

export default function Dashboard() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading]   = useState(true);
  const [series, setSeries]     = useState<string>("");
  const [variant, setVariant]   = useState<string>("");

  async function load() {
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    if (series)  params.set("series", series);
    if (variant) params.set("variant", variant);
    const res = await fetch(`/api/listings?${params}`);
    const json = await res.json();
    setListings(json.data || []);
    setLoading(false);
  }

  useEffect(() => { load(); }, [series, variant]); // eslint-disable-line

  const avgPrice = listings.length
    ? listings.reduce((s, l) => s + (l.price_idr || 0), 0) / listings.length
    : 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Dashboard</h1>
        <p className="text-sm text-[#737373] mt-1">{listings.length} listings terbaru</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total" value={listings.length.toString()} />
        <StatCard label="Avg Price" value={avgPrice ? `${(avgPrice / 1e6).toFixed(1)}M` : "—"} />
        <StatCard
          label="Series"
          value={series || "All"}
        />
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <select
          className="input flex-1 text-sm"
          value={series}
          onChange={(e) => setSeries(e.target.value)}
        >
          <option value="">Semua Series</option>
          {[11, 12, 13, 14, 15, 16, 17].map((s) => (
            <option key={s} value={s}>iPhone {s}</option>
          ))}
        </select>
        <select
          className="input flex-1 text-sm"
          value={variant}
          onChange={(e) => setVariant(e.target.value)}
        >
          <option value="">Semua Variant</option>
          {["SE", "Regular", "Plus", "Mini", "Pro", "Pro Max"].map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="card text-center text-[#737373] py-10">Loading...</div>
      ) : listings.length === 0 ? (
        <div className="card text-center text-[#737373] py-10">Tidak ada data</div>
      ) : (
        <div className="space-y-2">
          {listings.map((l) => (
            <ListingRow key={l.id} listing={l} />
          ))}
        </div>
      )}
    </div>
  );
}

function ListingRow({ listing: l }: { listing: Listing }) {
  return (
    <div className="card flex items-start justify-between gap-2">
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-sm truncate">
          {l.model} {l.storage_gb}GB
        </div>
        <div className="text-xs text-[#737373] mt-0.5 truncate">
          {l.color} · {l.origin_type} · {l.regional_code}
        </div>
        <div className="text-xs text-[#525252] mt-0.5">
          BH {l.battery_health}% · {l.date_posted}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-bold text-sm">{l.price_idr ? fmt(l.price_idr) : "—"}</div>
        <div className="text-xs text-[#525252] mt-0.5">{l.source_code}</div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card text-center">
      <div className="text-lg font-bold">{value}</div>
      <div className="text-xs text-[#737373] mt-0.5">{label}</div>
    </div>
  );
}
