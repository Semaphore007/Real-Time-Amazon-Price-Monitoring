"use client";

import React, { useEffect, useState } from "react";
import { Search, ExternalLink } from "lucide-react";
import Card from "@/components/Card";
import { api, Product, ProductDetail } from "@/lib/api";

const LOCATION_LABELS: Record<string, string> = {
  "600001": "Chennai",
  "560001": "Bangalore",
  "110001": "Delhi",
};

function fmt(v: number | null | undefined) {
  if (v == null) return "N/A";
  return `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function Loader() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
      <div className="animate-spin" style={{ width: 28, height: 28, borderRadius: "50%", border: "3px solid var(--border)", borderTopColor: "#3b82f6" }} />
    </div>
  );
}

function ProductCard({ product, onSelect }: { product: Product; onSelect: (asin: string) => void }) {
  const [detail, setDetail] = useState<ProductDetail | null>(null);

  useEffect(() => {
    api.product(product.asin).then(setDetail).catch(() => {});
  }, [product.asin]);

  return (
    <div
      onClick={() => onSelect(product.asin)}
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: 20,
        cursor: "pointer",
        transition: "all 0.18s ease",
        position: "relative",
        overflow: "hidden",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "#3b82f6";
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 8px 32px rgba(59,130,246,0.12)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Glow top-right */}
      <div style={{ position: "absolute", top: 0, right: 0, width: 100, height: 100, background: "radial-gradient(circle at 100% 0%,rgba(59,130,246,0.08),transparent 70%)", pointerEvents: "none" }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "#3b82f6", background: "rgba(59,130,246,0.12)", padding: "3px 8px", borderRadius: 6, letterSpacing: "0.05em" }}>
          {product.asin}
        </span>
        <ExternalLink size={14} color="var(--text-muted)" />
      </div>

      <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.4, marginBottom: 8 }}>
        {product.title}
      </h3>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {product.brand && (
          <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--bg-surface)", padding: "2px 8px", borderRadius: 5 }}>
            {product.brand}
          </span>
        )}
        {product.category && (
          <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--bg-surface)", padding: "2px 8px", borderRadius: 5 }}>
            {product.category}
          </span>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p style={{ fontSize: 11, color: "var(--text-muted)" }}>Latest Price</p>
          <p style={{ fontSize: 20, fontWeight: 700, color: "#10b981" }}>{fmt(detail?.latest_price)}</p>
        </div>
        <div style={{ textAlign: "right" }}>
          <p style={{ fontSize: 11, color: "var(--text-muted)" }}>Buy Box Events</p>
          <p style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>{detail?.buy_box_events ?? "—"}</p>
        </div>
      </div>
    </div>
  );
}

function OfferTable({ asin }: { asin: string }) {
  const [offers, setOffers] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.offers(asin).then(d => { setOffers(d as unknown as Record<string,unknown>[]); setLoading(false); }).catch(() => setLoading(false));
  }, [asin]);

  if (loading) return <Loader />;

  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
        All seller offers for <strong style={{ color: "var(--text-primary)" }}>{asin}</strong>
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {offers.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No offers found.</p>}
        {offers.map((o, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "12px 16px", borderRadius: 10,
            background: o.is_buy_box ? "rgba(16,185,129,0.08)" : "var(--bg-surface)",
            border: o.is_buy_box ? "1px solid rgba(16,185,129,0.3)" : "1px solid var(--border-muted)",
          }}>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{o.seller_name as string}</p>
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                {LOCATION_LABELS[o.location as string] ?? o.location ?? "All"} ·{" "}
                {o.is_fba ? <span style={{ color: "#3b82f6", fontWeight: 600 }}>FBA</span> : "MFN"} ·{" "}
                {o.availability as string}
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <p style={{ fontSize: 17, fontWeight: 700, color: o.is_buy_box ? "#10b981" : "var(--text-primary)" }}>
                {fmt(o.offer_price as number | null)}
              </p>
              {Boolean(o.is_buy_box) ? (
                <span style={{ fontSize: 9, fontWeight: 700, color: "#10b981", background: "rgba(16,185,129,0.15)", padding: "1px 6px", borderRadius: 4 }}>
                  BUY BOX
                </span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProductsClient() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    api.products().then(p => { setProducts(p); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const filtered = products.filter(p =>
    p.asin.toLowerCase().includes(search.toLowerCase()) ||
    (p.title ?? "").toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <Loader />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }} className="animate-fade-in">
      {/* Search bar */}
      <div style={{ position: "relative", maxWidth: 420 }}>
        <Search size={16} color="var(--text-muted)" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)" }} />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by ASIN or title…"
          style={{
            width: "100%", paddingLeft: 38, paddingRight: 14, paddingTop: 10, paddingBottom: 10,
            background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10,
            color: "var(--text-primary)", fontSize: 13, outline: "none",
          }}
        />
      </div>

      {/* Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 16 }}>
        {filtered.map(p => (
          <ProductCard key={p.asin} product={p} onSelect={setSelected} />
        ))}
        {filtered.length === 0 && (
          <p style={{ color: "var(--text-muted)", gridColumn: "1/-1" }}>No products match your search.</p>
        )}
      </div>

      {/* Offer drawer */}
      {selected && (
        <Card
          title={`Seller Offers · ${selected}`}
          action={
            <button onClick={() => setSelected(null)} style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
              ✕ Close
            </button>
          }
        >
          <OfferTable asin={selected} />
        </Card>
      )}
    </div>
  );
}
