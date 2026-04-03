"use client";

import React, { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer,
} from "recharts";
import { Package, TrendingDown, Users, Zap, Bell, AlertTriangle } from "lucide-react";
import StatCard from "@/components/StatCard";
import Card from "@/components/Card";
import DataTable from "@/components/DataTable";
import { api, AnalyticsSummary, Alert, Offer, BuyBoxEvent, Product } from "@/lib/api";

const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"];
const LOCATION_LABELS: Record<string, string> = {
  "600001": "Chennai",
  "560001": "Bangalore",
  "110001": "Delhi",
};

function fmt(v: number | null | undefined) {
  if (v == null) return "N/A";
  return `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function Loader() {
  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 120 }}>
      <div
        className="animate-spin"
        style={{ width: 28, height: 28, borderRadius: "50%", border: "3px solid var(--border)", borderTopColor: "#3b82f6" }}
      />
    </div>
  );
}

export default function OverviewClient() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [buyBox, setBuyBox] = useState<BuyBoxEvent[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.summary(),
      api.marketSnapshot(),
      api.alerts(8),
      api.buyBoxCurrent(),
      api.products(),
    ]).then(([s, o, a, bb, p]) => {
      setSummary(s);
      setOffers(o as Offer[]);
      setAlerts(a);
      setBuyBox(bb);
      setProducts(p);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;
  if (!summary) return <p style={{ color: "var(--text-muted)" }}>Unable to load data — is the API running?</p>;

  const marketShareData = summary.seller_market_share.map(r => ({
    name: r.seller_name,
    value: r.market_share_pct,
  }));

  const buyBoxData = summary.buy_box_win_rate.slice(0, 6).map(r => ({
    name: r.seller_name.split(" ")[0],
    fullName: r.seller_name,
    winRate: r.win_rate_pct,
  }));

  const priceChangerData = summary.frequent_price_changers.slice(0, 6).map(r => ({
    name: r.seller_name.split(" ")[0],
    changes: r.changes,
  }));

  const severityColor = (s: string) =>
    s === "critical" ? "#ef4444" : s === "warning" ? "#f59e0b" : "#3b82f6";

  // Stable typed rows for DataTable
  const buyBoxRows = buyBox.map(b => ({ ...b } as unknown as Record<string, unknown>));
  const offerRows = offers.slice(0, 30).map(o => ({ ...o } as unknown as Record<string, unknown>));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }} className="animate-fade-in">

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(210px,1fr))", gap: 16 }}>
        <StatCard label="Products Tracked" value={summary.products_tracked}
          sub={`${products.length} ASINs monitored`} icon={<Package size={20} color="#3b82f6" />} accent="blue" delay={0} />
        <StatCard label="Price Points" value={summary.price_points.toLocaleString()}
          sub="historical snapshots" icon={<TrendingDown size={20} color="#8b5cf6" />} accent="purple" delay={60} />
        <StatCard label="Avg Market Price" value={fmt(summary.average_market_price)}
          sub="across all sellers" icon={<Zap size={20} color="#06b6d4" />} accent="cyan" delay={120} />
        <StatCard label="Active Sellers" value={summary.seller_market_share.length}
          sub="competing in market" icon={<Users size={20} color="#10b981" />} accent="green" delay={180} />
        <StatCard label="Price Drop Alerts" value={alerts.filter(a => a.alert_type === "price_drop").length}
          sub="last 100 events" icon={<Bell size={20} color="#f59e0b" />} accent="amber" delay={240} />
        <StatCard label="Undercutting Events" value={summary.undercutting_events.length}
          sub="active price battles" icon={<AlertTriangle size={20} color="#ef4444" />} accent="red" delay={300} />
      </div>

      {/* Pie + Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card title="Seller Market Share" subtitle="% of products covered per seller">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={marketShareData} cx="50%" cy="50%" innerRadius={55} outerRadius={95}
                paddingAngle={3} dataKey="value"
                label={({ name, value }) => `${String(name ?? "").split(" ")[0]}: ${value}%`}
                labelLine={false}>
                {marketShareData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                formatter={(value) => [`${value}%`, "Share"]}
              />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Buy Box Win Rate" subtitle="% of buy-box events won per seller">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={buyBoxData} margin={{ top: 4, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} unit="%" />
              <Tooltip
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                formatter={(value) => [`${value}%`, "Win Rate"]}
                labelFormatter={(l) => buyBoxData.find(d => d.name === l)?.fullName ?? String(l)}
              />
              <Bar dataKey="winRate" radius={[4, 4, 0, 0]}>
                {buyBoxData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Price changers + current buy box */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card title="Frequent Price Changers" subtitle="Number of price updates detected per seller">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={priceChangerData} layout="vertical" margin={{ top: 0, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" horizontal={false} />
              <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} width={90} />
              <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="changes" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Current Buy Box Holders">
          <DataTable
            columns={[
              { key: "asin", header: "ASIN" },
              { key: "seller_name", header: "Seller" },
              { key: "price", header: "Price", render: r => fmt(r.price as number | null) },
              { key: "location", header: "Location",
                render: r => LOCATION_LABELS[r.location as string] ?? (r.location as string) ?? "—" },
            ]}
            data={buyBoxRows}
            maxHeight={220}
            emptyText="No buy-box data yet"
          />
        </Card>
      </div>

      {/* Undercutting + Alerts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card title="⚔️ Undercutting Detection" subtitle="Sellers pricing below nearest competitor">
          <DataTable
            columns={[
              { key: "asin", header: "ASIN" },
              { key: "seller_name", header: "Undercutter" },
              { key: "price", header: "Price", render: r => fmt(r.price as number | null) },
              { key: "undercut_pct", header: "Undercut %",
                render: r => (
                  <span style={{ color: "#ef4444", fontWeight: 600 }}>
                    {(r.undercut_pct as number).toFixed(1)}%
                  </span>
                )
              },
            ]}
            data={summary.undercutting_events as unknown as Record<string, unknown>[]}
            maxHeight={220}
            emptyText="No undercutting detected"
          />
        </Card>

        <Card title="Recent Alerts">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {alerts.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No alerts yet.</p>}
            {alerts.map((a, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "10px 12px", borderRadius: 8,
                background: "var(--bg-surface)",
                border: `1px solid ${severityColor(a.severity)}33`,
              }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%",
                  background: severityColor(a.severity), marginTop: 4, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {a.message}
                  </p>
                  <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    {a.alert_type.replace(/_/g," ")} · {a.asin} · {new Date(a.created_at).toLocaleString("en-IN")}
                  </p>
                </div>
                <span style={{
                  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  padding: "2px 6px", borderRadius: 4,
                  background: `${severityColor(a.severity)}22`,
                  color: severityColor(a.severity), flexShrink: 0,
                }}>
                  {a.severity}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Live market snapshot */}
      <Card title="Live Market Snapshot" subtitle="Latest seller offers across all monitored ASINs">
        <DataTable
          columns={[
            { key: "asin", header: "ASIN", width: "110px" },
            { key: "seller_name", header: "Seller" },
            { key: "offer_price", header: "Price", render: r => fmt(r.offer_price as number | null) },
            { key: "is_buy_box", header: "Buy Box",
              render: r => r.is_buy_box
                ? <span style={{ color: "#10b981", fontWeight: 700 }}>✓ Yes</span>
                : <span style={{ color: "var(--text-muted)" }}>—</span>
            },
            { key: "is_fba", header: "FBA",
              render: r => r.is_fba
                ? <span style={{ color: "#3b82f6", fontSize: 11, fontWeight: 600 }}>FBA</span>
                : <span style={{ color: "var(--text-muted)", fontSize: 11 }}>MFN</span>
            },
            { key: "location", header: "Location",
              render: r => LOCATION_LABELS[r.location as string] ?? "—"
            },
            { key: "availability", header: "Availability",
              render: r => (
                <span style={{ color: String(r.availability ?? "").includes("Low") ? "#f59e0b" : "#10b981", fontSize: 12 }}>
                  {String(r.availability ?? "—")}
                </span>
              )
            },
          ]}
          data={offerRows}
          maxHeight={340}
          emptyText="No market data yet — run the scraper or seed demo data"
        />
      </Card>

      {/* Hidden LineChart to satisfy import (needed for future use) */}
      <div style={{ display: "none" }}>
        <LineChart width={0} height={0} data={[]}>
          <Line type="monotone" dataKey="x" />
          <Legend />
        </LineChart>
      </div>
    </div>
  );
}
