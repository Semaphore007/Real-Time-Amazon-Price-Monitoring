"use client";
import React from "react";
import clsx from "clsx";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: React.ReactNode;
  accent?: "blue" | "purple" | "cyan" | "green" | "amber" | "red";
  trend?: number;      // positive = up, negative = down
  delay?: number;      // animation delay ms
}

const ACCENT_STYLES: Record<string, { border: string; glow: string; icon: string }> = {
  blue:   { border: "#3b82f6", glow: "rgba(59,130,246,0.15)",   icon: "rgba(59,130,246,0.18)" },
  purple: { border: "#8b5cf6", glow: "rgba(139,92,246,0.15)",   icon: "rgba(139,92,246,0.18)" },
  cyan:   { border: "#06b6d4", glow: "rgba(6,182,212,0.15)",    icon: "rgba(6,182,212,0.18)" },
  green:  { border: "#10b981", glow: "rgba(16,185,129,0.15)",   icon: "rgba(16,185,129,0.18)" },
  amber:  { border: "#f59e0b", glow: "rgba(245,158,11,0.15)",   icon: "rgba(245,158,11,0.18)" },
  red:    { border: "#ef4444", glow: "rgba(239,68,68,0.15)",    icon: "rgba(239,68,68,0.18)" },
};

export default function StatCard({ label, value, sub, icon, accent = "blue", trend, delay = 0 }: StatCardProps) {
  const a = ACCENT_STYLES[accent];
  return (
    <div
      className="animate-fade-in"
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${a.border}33`,
        borderRadius: 14,
        padding: "20px 22px",
        position: "relative",
        overflow: "hidden",
        transition: "transform 0.2s,box-shadow 0.2s",
        animationDelay: `${delay}ms`,
        cursor: "default",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${a.glow}`;
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* background glow */}
      <div style={{
        position: "absolute", top: 0, right: 0, width: 120, height: 120,
        background: `radial-gradient(circle at 100% 0%, ${a.glow}, transparent 70%)`,
        pointerEvents: "none",
      }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>
            {label}
          </p>
          <p style={{ fontSize: 28, fontWeight: 700, color: "var(--text-primary)", marginTop: 6, lineHeight: 1 }}>
            {value}
          </p>
          {sub && (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6 }}>
              {sub}
            </p>
          )}
          {typeof trend === "number" && (
            <p style={{ fontSize: 12, marginTop: 6, color: trend >= 0 ? "var(--success)" : "var(--danger)", fontWeight: 600 }}>
              {trend >= 0 ? "▲" : "▼"} {Math.abs(trend).toFixed(1)}% vs prev period
            </p>
          )}
        </div>
        {icon && (
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: a.icon,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
