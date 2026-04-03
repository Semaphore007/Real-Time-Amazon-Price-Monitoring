"use client";

import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import Card from "@/components/Card";
import { api, Alert } from "@/lib/api";
import { Bell, AlertTriangle, Info, Zap, Filter } from "lucide-react";

const SEV_STYLES: Record<string,{bg:string,border:string,color:string,icon:React.ReactNode}> = {
  critical: {bg:'rgba(239,68,68,0.08)',   border:'rgba(239,68,68,0.3)',   color:'#ef4444', icon:<AlertTriangle size={14}/>},
  warning:  {bg:'rgba(245,158,11,0.08)',  border:'rgba(245,158,11,0.3)',  color:'#f59e0b', icon:<Bell size={14}/>},
  info:     {bg:'rgba(59,130,246,0.08)',   border:'rgba(59,130,246,0.3)',  color:'#3b82f6', icon:<Info size={14}/>},
};
const TYPE_COLORS: Record<string,string> = {
  price_drop:'#ef4444', buy_box_change:'#8b5cf6', undercut:'#f59e0b', stock_change:'#06b6d4',
};
const LOCATION_LABELS:Record<string,string>= {"600001":"Chennai","560001":"Bangalore","110001":"Delhi"};

function Loader(){return <div style={{display:'flex',justifyContent:'center',padding:60}}><div className="animate-spin" style={{width:28,height:28,borderRadius:'50%',border:'3px solid var(--border)',borderTopColor:'#3b82f6'}}/></div>}

export default function AlertsClient() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterSev, setFilterSev] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [ws, setWs] = useState<WebSocket|null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    api.alerts(500).then(a => { setAlerts(a); setLoading(false); }).catch(()=>setLoading(false));
  }, []);

  // WebSocket live updates
  useEffect(() => {
    const wsUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/^http/,"ws") + "/ws/alerts";
    try {
      const socket = new WebSocket(wsUrl);
      socket.onopen = () => setLive(true);
      socket.onclose = () => setLive(false);
      socket.onerror = () => setLive(false);
      socket.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "alerts" && Array.isArray(msg.data)) {
            setAlerts(prev => {
              const newAlerts = msg.data as Alert[];
              const existing = new Set(prev.map((a:Alert)=>a.created_at+a.message));
              const fresh = newAlerts.filter(a => !existing.has(a.created_at+a.message));
              return [...fresh, ...prev];
            });
          }
        } catch {}
      };
      setWs(socket);
      return () => socket.close();
    } catch { return undefined; }
  }, []);

  const filtered = alerts.filter(a =>
    (filterSev === "all" || a.severity === filterSev) &&
    (filterType === "all" || a.alert_type === filterType)
  );

  // Chart: counts by type
  const byType = Object.entries(
    alerts.reduce<Record<string,number>>((acc,a) => { acc[a.alert_type]=(acc[a.alert_type]||0)+1; return acc; }, {})
  ).map(([type,count])=>({type:type.replace(/_/g," "),count,raw:type}))
   .sort((a,b)=>b.count-a.count);

  if (loading) return <Loader />;

  return (
    <div style={{display:'flex',flexDirection:'column',gap:20}} className="animate-fade-in">

      {/* Live WS status */}
      <div style={{display:'flex',alignItems:'center',gap:10,padding:'10px 16px',borderRadius:10,
        background:live?'rgba(16,185,129,0.08)':'rgba(100,116,139,0.08)',
        border:`1px solid ${live?'rgba(16,185,129,0.25)':'rgba(100,116,139,0.2)'}`}}>
        <span style={{width:8,height:8,borderRadius:'50%',background:live?'#10b981':'#64748b',display:'inline-block'}}/>
        <span style={{fontSize:12,color:live?'#10b981':'var(--text-muted)',fontWeight:600}}>
          {live ? 'Live WebSocket connected — alerts stream in real-time' : 'WebSocket offline — showing cached data'}
        </span>
      </div>

      {/* Summary + chart row */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20}}>

        {/* Counts */}
        <Card title="Alert Summary">
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
            {[
              {label:'Total',     value:alerts.length,                                       color:'var(--text-primary)'},
              {label:'Critical',  value:alerts.filter(a=>a.severity==='critical').length,     color:'#ef4444'},
              {label:'Warning',   value:alerts.filter(a=>a.severity==='warning').length,      color:'#f59e0b'},
              {label:'Info',      value:alerts.filter(a=>a.severity==='info').length,         color:'#3b82f6'},
              {label:'Price Drop',value:alerts.filter(a=>a.alert_type==='price_drop').length, color:'#ef4444'},
              {label:'Buy Box',   value:alerts.filter(a=>a.alert_type==='buy_box_change').length, color:'#8b5cf6'},
            ].map(item=>(
              <div key={item.label} style={{padding:'12px 14px',background:'var(--bg-surface)',borderRadius:9}}>
                <p style={{fontSize:10,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.05em'}}>{item.label}</p>
                <p style={{fontSize:22,fontWeight:700,color:item.color,marginTop:3}}>{item.value}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Alerts by Type">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={byType} margin={{top:4,right:10,left:-20,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" vertical={false}/>
              <XAxis dataKey="type" tick={{fill:'var(--text-muted)',fontSize:10}}/>
              <YAxis tick={{fill:'var(--text-muted)',fontSize:11}}/>
              <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}}/>
              <Bar dataKey="count" name="Count" radius={[4,4,0,0]}>
                {byType.map(d=><Cell key={d.raw} fill={TYPE_COLORS[d.raw]??'#3b82f6'}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Filters */}
      <div style={{display:'flex',gap:10,alignItems:'center'}}>
        <Filter size={14} color="var(--text-muted)" />
        <select value={filterSev} onChange={e=>setFilterSev(e.target.value)}
          style={{padding:'7px 12px',background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,color:'var(--text-primary)',fontSize:12,outline:'none'}}>
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select value={filterType} onChange={e=>setFilterType(e.target.value)}
          style={{padding:'7px 12px',background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,color:'var(--text-primary)',fontSize:12,outline:'none'}}>
          <option value="all">All Types</option>
          <option value="price_drop">Price Drop</option>
          <option value="buy_box_change">Buy Box Change</option>
          <option value="undercut">Undercut</option>
          <option value="stock_change">Stock Change</option>
        </select>
        <span style={{fontSize:12,color:'var(--text-muted)',marginLeft:'auto'}}>{filtered.length} events shown</span>
      </div>

      {/* Alert feed */}
      <div style={{display:'flex',flexDirection:'column',gap:8}}>
        {filtered.length === 0 && (
          <div style={{padding:40,textAlign:'center',color:'var(--text-muted)',border:'1px dashed var(--border)',borderRadius:12}}>
            No alerts match your filters.
          </div>
        )}
        {filtered.map((a,i)=>{
          const sev = SEV_STYLES[a.severity] ?? SEV_STYLES.info;
          return (
            <div key={i} style={{
              display:'flex',alignItems:'flex-start',gap:12,padding:'12px 16px',borderRadius:10,
              background:sev.bg,border:`1px solid ${sev.border}`,
              animation:`fadeIn 0.2s ease both`,animationDelay:`${Math.min(i*20,400)}ms`,
            }}>
              <div style={{color:sev.color,marginTop:2,flexShrink:0}}>{sev.icon}</div>
              <div style={{flex:1,minWidth:0}}>
                <p style={{fontSize:13,color:'var(--text-primary)',fontWeight:500,lineHeight:1.45}}>
                  {a.message}
                </p>
                <div style={{display:'flex',gap:10,marginTop:5,flexWrap:'wrap'}}>
                  <span style={{fontSize:10,color:'var(--text-muted)'}}>{a.asin}</span>
                  {a.seller_name && <span style={{fontSize:10,color:'var(--text-secondary)'}}>{a.seller_name}</span>}
                  {a.location && <span style={{fontSize:10,color:'var(--text-muted)'}}>{LOCATION_LABELS[a.location]??a.location}</span>}
                  <span style={{fontSize:10,color:'var(--text-muted)',marginLeft:'auto'}}>
                    {new Date(a.created_at).toLocaleString('en-IN')}
                  </span>
                </div>
              </div>
              <div style={{display:'flex',flexDirection:'column',gap:4,flexShrink:0,alignItems:'flex-end'}}>
                <span style={{fontSize:9,fontWeight:700,textTransform:'uppercase',padding:'2px 7px',borderRadius:5,
                  background:`${sev.color}22`,color:sev.color}}>
                  {a.severity}
                </span>
                <span style={{fontSize:9,color:'var(--text-muted)',padding:'2px 6px',borderRadius:4,
                  background:'var(--bg-surface)',textTransform:'lowercase'}}>
                  {a.alert_type.replace(/_/g," ")}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
