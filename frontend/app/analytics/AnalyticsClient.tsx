"use client";

import React, { useEffect, useState } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, Legend,
} from "recharts";
import Card from "@/components/Card";
import DataTable from "@/components/DataTable";
import { api, AnalyticsSummary } from "@/lib/api";

const COLORS=["#3b82f6","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];
function fmt(v:number|null|undefined){return v==null?'N/A':`₹${v.toLocaleString('en-IN',{minimumFractionDigits:2})}`}
function Loader(){return <div style={{display:'flex',justifyContent:'center',padding:60}}><div className="animate-spin" style={{width:28,height:28,borderRadius:'50%',border:'3px solid var(--border)',borderTopColor:'#3b82f6'}}/></div>}

interface HeatRow { seller_name:string; [loc:string]:number|string|null }

export default function AnalyticsClient() {
  const [summary, setSummary] = useState<AnalyticsSummary|null>(null);
  const [heatmap, setHeatmap] = useState<HeatRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.summary(), api.heatmap()])
      .then(([s,h]) => { setSummary(s); setHeatmap(h as HeatRow[]); setLoading(false); })
      .catch(()=>setLoading(false));
  }, []);

  if (loading) return <Loader />;
  if (!summary) return <p style={{color:'var(--text-muted)'}}>Could not load analytics data.</p>;

  /* Scatter data: seller vs avg market price */
  const scatterData = summary.seller_market_share.map(r => ({
    name: r.seller_name,
    x: r.market_share_pct,
    y: summary.buy_box_win_rate.find(b=>b.seller_name===r.seller_name)?.win_rate_pct ?? 0,
  }));

  /* Heatmap columns */
  const heatLocations = heatmap.length > 0
    ? Object.keys(heatmap[0]).filter(k => k !== "seller_name")
    : [];
  
  const LOCATION_LABELS:Record<string,string>= {"600001":"Chennai","560001":"Bangalore","110001":"Delhi"};

  function cellColor(val:number|null|undefined):string {
    if(val==null) return 'var(--bg-surface)';
    if(val<280) return 'rgba(16,185,129,0.35)';
    if(val<400) return 'rgba(59,130,246,0.25)';
    if(val<500) return 'rgba(245,158,11,0.25)';
    return 'rgba(239,68,68,0.25)';
  }

  return (
    <div style={{display:'flex',flexDirection:'column',gap:20}} className="animate-fade-in">

      {/* Summary KPIs */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(180px,1fr))',gap:14}}>
        {[
          {label:'Price Points',    value:summary.price_points.toLocaleString(),  accent:'#3b82f6'},
          {label:'Products Tracked',value:summary.products_tracked,               accent:'#8b5cf6'},
          {label:'Avg Market Price', value:fmt(summary.average_market_price),     accent:'#06b6d4'},
          {label:'Price Battles',   value:summary.undercutting_events.length,     accent:'#ef4444'},
        ].map(item => (
          <div key={item.label} style={{background:'var(--bg-card)',border:`1px solid ${item.accent}33`,borderRadius:14,padding:'18px 20px',borderTop:`3px solid ${item.accent}`}}>
            <p style={{fontSize:11,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.06em',fontWeight:600}}>{item.label}</p>
            <p style={{fontSize:26,fontWeight:700,color:'var(--text-primary)',marginTop:6}}>{item.value}</p>
          </div>
        ))}
      </div>

      {/* Scatter: market share vs buy-box */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20}}>
        <Card title="Market Share vs Buy Box Win Rate" subtitle="Each dot = one seller">
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{top:10,right:16,left:-10,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
              <XAxis dataKey="x" name="Market Share %" unit="%" tick={{fill:'var(--text-muted)',fontSize:11}} label={{value:'Market Share %',fill:'var(--text-muted)',fontSize:11,position:'insideBottom',offset:-4}} />
              <YAxis dataKey="y" name="Buy Box Win %" unit="%" tick={{fill:'var(--text-muted)',fontSize:11}} />
              <Tooltip cursor={{strokeDasharray:'3 3'}}
                contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:10,fontSize:12}}
                formatter={(v,n) => [`${(v as number).toFixed(1)}%`, String(n)]}
                labelFormatter={(_,p) => ((p as unknown) as {payload?:{name?:string}}[])?.[0]?.payload?.name ?? ''} />
              <Scatter data={scatterData} fill="#3b82f6">
                {scatterData.map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]} />)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Price Change Frequency" subtitle="Which sellers reprice most aggressively">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={summary.frequent_price_changers.slice(0,8)} margin={{top:4,right:10,left:-20,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" vertical={false} />
              <XAxis dataKey="seller_name" tick={{fill:'var(--text-muted)',fontSize:10}} tickFormatter={v=>v.split(" ")[0]} />
              <YAxis tick={{fill:'var(--text-muted)',fontSize:11}} />
              <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}} />
              <Bar dataKey="changes" name="Price Changes" radius={[4,4,0,0]}>
                {summary.frequent_price_changers.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Price Heatmap */}
      <Card title="Location × Seller Price Heatmap" subtitle="Lowest price per seller per city (greener = cheaper)">
        {heatmap.length === 0 ? (
          <p style={{color:'var(--text-muted)',padding:20}}>Not enough data for heatmap.</p>
        ) : (
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'separate',borderSpacing:4,fontSize:12}}>
              <thead>
                <tr>
                  <th style={{padding:'8px 14px',textAlign:'left',color:'var(--text-muted)',fontSize:11,textTransform:'uppercase'}}>Seller</th>
                  {heatLocations.map(loc=>(
                    <th key={loc} style={{padding:'8px 14px',color:'var(--text-muted)',fontSize:11,textTransform:'uppercase',textAlign:'center'}}>
                      {LOCATION_LABELS[loc]??loc}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmap.map((row,i)=>(
                  <tr key={i}>
                    <td style={{padding:'9px 14px',color:'var(--text-primary)',fontWeight:600,whiteSpace:'nowrap'}}>{row.seller_name}</td>
                    {heatLocations.map(loc=>{
                      const val = row[loc] as number|null;
                      return (
                        <td key={loc} style={{padding:'9px 14px',textAlign:'center',borderRadius:6,background:cellColor(val),color:'var(--text-primary)',fontWeight:500}}>
                          {val!=null?fmt(val):'—'}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{fontSize:11,color:'var(--text-muted)',marginTop:12}}>
              <span style={{color:'rgba(16,185,129,0.8)'}}>■</span> &lt;₹280 
              <span style={{color:'rgba(59,130,246,0.8)',marginLeft:10}}>■</span> ₹280–400 
              <span style={{color:'rgba(245,158,11,0.8)',marginLeft:10}}>■</span> ₹400–500 
              <span style={{color:'rgba(239,68,68,0.8)',marginLeft:10}}>■</span> ₹500+
            </p>
          </div>
        )}
      </Card>

      {/* Undercutting table */}
      <Card title="⚔️ Active Undercutting Events" subtitle="Sellers pricing significantly below the next competitor">
        <DataTable
          columns={[
            {key:'asin',        header:'ASIN'},
            {key:'seller_name', header:'Undercutter',render:r=><strong style={{color:'#ef4444'}}>{r.seller_name as string}</strong>},
            {key:'price',       header:'Their Price',  render:r=>fmt(r.price as number|null)},
            {key:'undercut_pct',header:'Undercut %',   render:r=>(
              <span style={{
                fontSize:12,fontWeight:700,color:'#ef4444',
                background:'rgba(239,68,68,0.12)',padding:'2px 8px',borderRadius:5}}>
                ↓ {(r.undercut_pct as number).toFixed(2)}%
              </span>
            )},
          ]}
          data={summary.undercutting_events as unknown as Record<string,unknown>[]}
          emptyText="No undercutting detected currently"
        />
      </Card>

      {/* Lowest price seller */}
      {summary.min_price_seller && (
        <div style={{
          padding:'16px 20px',borderRadius:14,
          background:'rgba(16,185,129,0.08)',border:'1px solid rgba(16,185,129,0.25)',
          display:'flex',gap:20,alignItems:'center',
        }}>
          <span style={{fontSize:28}}>🏆</span>
          <div>
            <p style={{fontSize:12,color:'var(--text-muted)'}}>Current Market Price Leader</p>
            <p style={{fontSize:16,fontWeight:700,color:'var(--text-primary)',marginTop:2}}>
              {summary.min_price_seller.seller_name}
            </p>
            <p style={{fontSize:13,color:'#10b981',fontWeight:600,marginTop:2}}>
              {fmt(summary.min_price_seller.offer_price)} on {summary.min_price_seller.asin}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
