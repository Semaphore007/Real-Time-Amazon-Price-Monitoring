"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceLine, Brush,
} from "recharts";
import Card from "@/components/Card";
import StatCard from "@/components/StatCard";
import { api, Product, PriceTrend } from "@/lib/api";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

const COLORS = ["#3b82f6","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];
const LOCATION_LABELS: Record<string,string> = { "600001":"Chennai","560001":"Bangalore","110001":"Delhi" };

function fmt(v:number|null|undefined){ return v==null?'N/A':`₹${v.toLocaleString('en-IN',{minimumFractionDigits:2})}` }

function Loader(){return <div style={{display:'flex',justifyContent:'center',padding:60}}><div className="animate-spin" style={{width:28,height:28,borderRadius:'50%',border:'3px solid var(--border)',borderTopColor:'#3b82f6'}}/></div>}

export default function PricesClient() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedAsin, setSelectedAsin] = useState<string>("");
  const [selectedLocation, setSelectedLocation] = useState<string>("");
  const [trend, setTrend] = useState<PriceTrend | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.products().then(p => {
      setProducts(p);
      if (p.length > 0) setSelectedAsin(p[0].asin);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedAsin) return;
    setTrend(null);
    api.priceTrends(selectedAsin).then(setTrend).catch(() => {});
  }, [selectedAsin]);

  /* Build chart-friendly data: rows keyed by date, columns by seller */
  const chartData = useMemo(() => {
    if (!trend || trend.trends.length === 0) return [];
    const byDate: Record<string, Record<string, number>> = {};
    for (const row of trend.trends) {
      if (!byDate[row.date]) byDate[row.date] = {};
      byDate[row.date][row.seller_name] = row.price;
    }
    return Object.entries(byDate)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, sellers]) => ({ date, ...sellers }));
  }, [trend]);

  const sellers = useMemo(() => {
    if (!trend) return [];
    return [...new Set(trend.trends.map(r => r.seller_name))];
  }, [trend]);

  if (loading) return <Loader />;

  const rangeSpread = trend ? trend.overall_max - trend.overall_min : 0;
  const rangeColor = rangeSpread > 50 ? "red" : rangeSpread > 20 ? "amber" : "green";

  return (
    <div style={{display:'flex',flexDirection:'column',gap:20}} className="animate-fade-in">

      {/* Controls */}
      <div style={{display:'flex',gap:12,flexWrap:'wrap'}}>
        <select
          value={selectedAsin}
          onChange={e => setSelectedAsin(e.target.value)}
          style={{padding:'9px 14px',background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:10,color:'var(--text-primary)',fontSize:13,minWidth:280,outline:'none'}}
        >
          {products.map(p => <option key={p.asin} value={p.asin}>{p.asin} · {p.title}</option>)}
        </select>

        <select
          value={selectedLocation}
          onChange={e => setSelectedLocation(e.target.value)}
          style={{padding:'9px 14px',background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:10,color:'var(--text-primary)',fontSize:13,outline:'none'}}
        >
          <option value="">All Locations</option>
          {Object.entries(LOCATION_LABELS).map(([k,v]) => <option key={k} value={k}>{v} ({k})</option>)}
        </select>
      </div>

      {/* KPIs */}
      {trend && (
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(180px,1fr))',gap:14}}>
          <StatCard label="Min Price" value={fmt(trend.overall_min)} accent="green"
            icon={<TrendingDown size={18} color="#10b981" />} />
          <StatCard label="Max Price" value={fmt(trend.overall_max)} accent="red"
            icon={<TrendingUp size={18} color="#ef4444" />} />
          <StatCard label="Avg Price" value={fmt(trend.overall_avg)} accent="blue"
            icon={<Minus size={18} color="#3b82f6" />} />
          <StatCard label="Price Range" value={fmt(rangeSpread)} accent={rangeColor as "red"|"amber"|"green"}
            sub="max − min spread" />
        </div>
      )}

      {/* Main line chart */}
      <Card title="Price Trend Over Time" subtitle="All competing sellers on same chart — 30-day history">
        {!trend ? <Loader /> : chartData.length === 0 ? (
          <p style={{color:'var(--text-muted)',padding:20}}>No trend data available for this product.</p>
        ) : (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={chartData} margin={{top:8,right:16,left:0,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
              <XAxis dataKey="date" tick={{fill:'var(--text-muted)',fontSize:10}} tickFormatter={d => d.slice(5)} />
              <YAxis tick={{fill:'var(--text-muted)',fontSize:11}} tickFormatter={v => `₹${v}`} />
              <Tooltip
                contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:10,fontSize:12}}
                formatter={(v) => [fmt(v as number)]}
              />
              <Legend wrapperStyle={{fontSize:12,color:'var(--text-secondary)'}} />
              <Brush dataKey="date" height={22} stroke="var(--border)" fill="var(--bg-surface)"
                travellerWidth={6} />
              {sellers.map((s,i) => (
                <Line key={s} type="monotone" dataKey={s} stroke={COLORS[i%COLORS.length]}
                  strokeWidth={2} dot={false} activeDot={{r:5}} connectNulls />
              ))}
              {trend && <ReferenceLine y={trend.overall_avg} stroke="rgba(255,255,255,0.2)" strokeDasharray="6 3" label={{value:'Avg',fill:'var(--text-muted)',fontSize:10}} />}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Data table */}
      {trend && trend.trends.length > 0 && (
        <Card title="Raw Price Points" subtitle="Underlying data — most recent 200 rows">
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
              <thead>
                <tr style={{background:'var(--bg-surface)'}}>
                  {['Date','Seller','Price (₹)'].map(h => (
                    <th key={h} style={{padding:'8px 14px',textAlign:'left',color:'var(--text-muted)',fontSize:11,textTransform:'uppercase',borderBottom:'1px solid var(--border)'}}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trend.trends.slice(-200).reverse().map((r,i) => (
                  <tr key={i} style={{borderBottom:'1px solid var(--border-muted)'}}
                    onMouseEnter={e=>(e.currentTarget.style.background='var(--bg-card-hover)')}
                    onMouseLeave={e=>(e.currentTarget.style.background='transparent')}
                  >
                    <td style={{padding:'7px 14px',color:'var(--text-secondary)'}}>{r.date}</td>
                    <td style={{padding:'7px 14px',color:'var(--text-primary)',fontWeight:500}}>{r.seller_name}</td>
                    <td style={{padding:'7px 14px',color:'#10b981',fontWeight:600}}>{fmt(r.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
