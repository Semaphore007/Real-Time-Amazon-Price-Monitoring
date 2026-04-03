"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import Card from "@/components/Card";
import DataTable from "@/components/DataTable";
import { api, Product, BuyBoxEvent, BuyBoxOwnership } from "@/lib/api";

const COLORS = ["#3b82f6","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];
const LOCATION_LABELS:Record<string,string>= {"600001":"Chennai","560001":"Bangalore","110001":"Delhi"};
function fmt(v:number|null|undefined){return v==null?'N/A':`₹${v.toLocaleString('en-IN',{minimumFractionDigits:2})}`}
function Loader(){return <div style={{display:'flex',justifyContent:'center',padding:60}}><div className="animate-spin" style={{width:28,height:28,borderRadius:'50%',border:'3px solid var(--border)',borderTopColor:'#3b82f6'}}/></div>}

export default function BuyBoxClient() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedAsin, setSelectedAsin] = useState("");
  const [history, setHistory] = useState<BuyBoxEvent[]>([]);
  const [current, setCurrent] = useState<BuyBoxEvent[]>([]);
  const [ownership, setOwnership] = useState<BuyBoxOwnership[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.products(), api.buyBoxCurrent(), api.buyBoxOwnership()])
      .then(([p, c, o]) => {
        setProducts(p);
        setCurrent(c);
        setOwnership(o as unknown as BuyBoxOwnership[]);
        if (p.length > 0) setSelectedAsin(p[0].asin);
        setLoading(false);
      }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedAsin) return;
    setHistory([]);
    api.buyBoxHistory(selectedAsin).then(h => setHistory(h)).catch(()=>{});
  }, [selectedAsin]);

  // Timeline: price over time colored by seller
  const timelineData = useMemo(() => {
    if (history.length === 0) return [];
    return history.map(h => ({
      date: new Date(h.captured_at).toLocaleDateString("en-IN",{month:"short",day:"numeric"}),
      price: h.price,
      seller: h.seller_name,
      location: LOCATION_LABELS[h.location ?? ""] ?? h.location,
    }));
  }, [history]);

  // Ownership breakdown for selected ASIN
  const ownershipForAsin = useMemo(() => {
    return ownership.filter(o => o.asin === selectedAsin);
  }, [ownership, selectedAsin]);

  // All-ASINs ownership for global pie
  const globalOwnership = useMemo(() => {
    const map: Record<string,number> = {};
    ownership.forEach(o => { map[o.seller_name] = (map[o.seller_name]||0) + o.events; });
    return Object.entries(map).map(([name,events]) => ({name, events})).sort((a,b)=>b.events-a.events);
  }, [ownership]);

  if (loading) return <Loader />;

  return (
    <div style={{display:'flex',flexDirection:'column',gap:20}} className="animate-fade-in">

      {/* Global ownership pie + current holders */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20}}>

        <Card title="Global Buy Box Ownership" subtitle="All ASINs combined — total events per seller">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={globalOwnership} cx="50%" cy="50%" outerRadius={95} innerRadius={50}
                dataKey="events" paddingAngle={3}
                label={({name,percent}) => `${String(name ?? "").split(" ")[0]} ${((percent ?? 0)*100).toFixed(0)}%`}
                labelLine={false}
              >
                {globalOwnership.map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}}
                formatter={(v,n) => [`${(v as number)} events`, String(n)]} />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Current Buy Box Holders" subtitle="Who holds buy-box right now per ASIN">
          <DataTable
            columns={[
              {key:'asin',header:'ASIN'},
              {key:'seller_name',header:'Seller',render:r=><strong style={{color:'#10b981'}}>{r.seller_name as string}</strong>},
              {key:'price',header:'Price',render:r=>fmt(r.price as number|null)},
              {key:'location',header:'Location',render:r=>LOCATION_LABELS[r.location as string]??r.location??'—'},
            ]}
            data={current as unknown as Record<string,unknown>[]}
            maxHeight={220}
          />
        </Card>
      </div>

      {/* ASIN selector + price timeline */}
      <Card
        title="Buy Box Price Timeline"
        subtitle="Price of the buy-box winner over time"
        action={
          <select value={selectedAsin} onChange={e=>setSelectedAsin(e.target.value)}
            style={{padding:'6px 12px',background:'var(--bg-surface)',border:'1px solid var(--border)',borderRadius:8,color:'var(--text-primary)',fontSize:12,outline:'none'}}>
            {products.map(p=><option key={p.asin} value={p.asin}>{p.asin}</option>)}
          </select>
        }
      >
        {history.length === 0 ? <p style={{color:'var(--text-muted)',padding:20}}>No buy-box history for this ASIN.</p> : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={timelineData} margin={{top:8,right:16,left:0,bottom:0}}>
              <defs>
                <linearGradient id="bbGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
              <XAxis dataKey="date" tick={{fill:'var(--text-muted)',fontSize:10}} />
              <YAxis tick={{fill:'var(--text-muted)',fontSize:11}} tickFormatter={v=>`₹${v}`} />
              <Tooltip
                contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:10,fontSize:12}}
                formatter={(v,_n,p)=>[fmt(v as number|null), `Seller: ${(p as {payload?:{seller?:string}})?.payload?.seller ?? ''}`]}
              />
              <Area type="monotone" dataKey="price" stroke="#3b82f6" fill="url(#bbGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Ownership breakdown */}
      {ownershipForAsin.length > 0 && (
        <Card title={`Ownership Breakdown · ${selectedAsin}`} subtitle="Share of buy-box events per seller for this ASIN">
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(160px,1fr))',gap:12}}>
            {ownershipForAsin.map((o,i) => (
              <div key={o.seller_name} style={{background:'var(--bg-surface)',borderRadius:10,padding:'14px 16px',borderTop:`3px solid ${COLORS[i%COLORS.length]}`}}>
                <p style={{fontSize:12,fontWeight:600,color:'var(--text-primary)',marginBottom:6}}>{o.seller_name}</p>
                <p style={{fontSize:22,fontWeight:700,color:COLORS[i%COLORS.length]}}>{o.ownership_pct.toFixed(1)}<span style={{fontSize:13}}>%</span></p>
                <p style={{fontSize:10,color:'var(--text-muted)',marginTop:4}}>{o.events} of {o.total} events</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Raw history table */}
      <Card title="Buy Box Event Log" subtitle={`Full history for ${selectedAsin}`}>
        <DataTable
          columns={[
            {key:'seller_name',header:'Seller'},
            {key:'price',header:'Price',render:r=>fmt(r.price as number|null)},
            {key:'location',header:'Location',render:r=>LOCATION_LABELS[r.location as string]??r.location??'—'},
            {key:'captured_at',header:'Timestamp',render:r=>new Date(r.captured_at as string).toLocaleString('en-IN')},
          ]}
          data={[...history].reverse() as unknown as Record<string,unknown>[]}
          maxHeight={300}
          emptyText="No history for this product"
        />
      </Card>
    </div>
  );
}
