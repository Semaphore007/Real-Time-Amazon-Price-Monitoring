"use client";

import React, { useEffect, useState } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell,
} from "recharts";
import Card from "@/components/Card";
import DataTable from "@/components/DataTable";
import { api, Seller, SellerRanking } from "@/lib/api";

const COLORS = ["#3b82f6","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];

function Loader(){return <div style={{display:'flex',justifyContent:'center',padding:60}}><div className="animate-spin" style={{width:28,height:28,borderRadius:'50%',border:'3px solid var(--border)',borderTopColor:'#3b82f6'}}/></div>}

function Badge({v}:{v:string}){
  const c = v==='FBA'?{bg:'rgba(59,130,246,0.15)',color:'#3b82f6'}:{bg:'rgba(148,163,184,0.12)',color:'#94a3b8'};
  return <span style={{fontSize:10,fontWeight:700,padding:'2px 7px',borderRadius:5,background:c.bg,color:c.color}}>{v}</span>;
}

export default function SellersClient() {
  const [sellers, setSellers] = useState<Seller[]>([]);
  const [ranking, setRanking] = useState<SellerRanking[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.sellers(), api.sellerRanking()])
      .then(([s,r]) => { setSellers(s); setRanking(r); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;

  const rankingEnriched = ranking.map(r => {
    const s = sellers.find(x => x.seller_name === r.seller_name);
    return { ...r, rating: s?.rating ?? null, fulfillment_type: s?.fulfillment_type ?? null };
  });

  const radarData = ranking.slice(0,6).map(r => ({
    seller: r.seller_name.split(" ")[0],
    "Buy Box %": r.buy_box_win_rate_pct,
    "Market Share %": r.market_share_pct,
  }));

  return (
    <div style={{display:'flex',flexDirection:'column',gap:20}} className="animate-fade-in">

      {/* Top seller podium */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))',gap:14}}>
        {rankingEnriched.slice(0,6).map((r,i) => (
          <div key={r.seller_name} style={{
            background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,
            padding:'18px 20px',position:'relative',overflow:'hidden',
            borderTop:`3px solid ${COLORS[i%COLORS.length]}`,
          }}>
            <div style={{position:'absolute',top:12,right:12,width:28,height:28,borderRadius:'50%',
              background:COLORS[i%COLORS.length],display:'flex',alignItems:'center',justifyContent:'center'}}>
              <span style={{fontSize:12,fontWeight:800,color:'#fff'}}>#{i+1}</span>
            </div>
            <p style={{fontSize:13,fontWeight:700,color:'var(--text-primary)',marginBottom:4,paddingRight:36,lineHeight:1.3}}>
              {r.seller_name}
            </p>
            {r.fulfillment_type && <Badge v={r.fulfillment_type} />}
            <div style={{marginTop:12,display:'flex',flexDirection:'column',gap:5}}>
              <div style={{display:'flex',justifyContent:'space-between', fontSize:11}}>
                <span style={{color:'var(--text-muted)'}}>Buy Box</span>
                <span style={{color:COLORS[i%COLORS.length],fontWeight:700}}>{r.buy_box_win_rate_pct.toFixed(1)}%</span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between', fontSize:11}}>
                <span style={{color:'var(--text-muted)'}}>Mkt Share</span>
                <span style={{color:'var(--text-secondary)',fontWeight:600}}>{r.market_share_pct.toFixed(1)}%</span>
              </div>
              {r.rating && (
                <div style={{display:'flex',justifyContent:'space-between', fontSize:11}}>
                  <span style={{color:'var(--text-muted)'}}>Rating</span>
                  <span style={{color:'#f59e0b',fontWeight:600}}>{'★'.repeat(Math.round(r.rating))} {r.rating}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20}}>

        <Card title="Performance Radar" subtitle="Buy Box % vs Market Share per seller">
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--border-muted)" />
              <PolarAngleAxis dataKey="seller" tick={{fill:'var(--text-secondary)',fontSize:11}} />
              <PolarRadiusAxis angle={30} domain={[0,80]} tick={{fill:'var(--text-muted)',fontSize:9}} />
              <Radar name="Buy Box %" dataKey="Buy Box %" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
              <Radar name="Market Share %" dataKey="Market Share %" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.20} />
              <Legend wrapperStyle={{fontSize:12,color:'var(--text-secondary)'}} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Buy Box Win Rate" subtitle="Ranked by total buy-box captures">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={ranking.slice(0,8)} margin={{top:4,right:10,left:-20,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" vertical={false} />
              <XAxis dataKey="seller_name" tick={{fill:'var(--text-muted)',fontSize:10}}
                tickFormatter={v => v.split(" ")[0]} />
              <YAxis tick={{fill:'var(--text-muted)',fontSize:11}} unit="%" />
              <Tooltip
                contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}}
                formatter={(v) => [`${(v as number).toFixed(1)}%`]}
              />
              <Bar dataKey="buy_box_win_rate_pct" name="Win Rate" radius={[4,4,0,0]}>
                {ranking.map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Full table */}
      <Card title="Seller Directory" subtitle="All sellers with fulfillment type and rating">
        <DataTable
          columns={[
            { key:'seller_name',       header:'Seller Name' },
            { key:'fulfillment_type',  header:'Fulfillment',   render:r => r.fulfillment_type ? <Badge v={r.fulfillment_type as string} /> : <span style={{color:'var(--text-muted)'}}>—</span> },
            { key:'rating',            header:'Rating',         render:r => r.rating ? <span style={{color:'#f59e0b',fontWeight:600}}>★ {(r.rating as number).toFixed(1)}</span> : <span style={{color:'var(--text-muted)'}}>—</span> },
            { key:'buy_box_win_rate_pct', header:'Buy Box Win%', render:r => {
                const rr = rankingEnriched.find(x=>x.seller_name===r.seller_name);
                return rr ? <span style={{color:'#3b82f6',fontWeight:600}}>{rr.buy_box_win_rate_pct.toFixed(1)}%</span> : <span style={{color:'var(--text-muted)'}}>—</span>;
              }
            },
            { key:'market_share_pct',  header:'Market Share%', render:r => {
                const rr = rankingEnriched.find(x=>x.seller_name===r.seller_name);
                return rr ? `${rr.market_share_pct.toFixed(1)}%` : '—';
              }
            },
          ]}
          data={sellers as unknown as Record<string,unknown>[]}
          emptyText="No sellers found"
        />
      </Card>
    </div>
  );
}
