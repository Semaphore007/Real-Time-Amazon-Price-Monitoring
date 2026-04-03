"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  TrendingUp,
  ShoppingCart,
  Users,
  Bell,
  BarChart2,
  Zap,
  Activity,
} from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/",              label: "Overview",      icon: LayoutDashboard },
  { href: "/products",      label: "Products",      icon: ShoppingCart },
  { href: "/prices",        label: "Price Trends",  icon: TrendingUp },
  { href: "/sellers",       label: "Sellers",       icon: Users },
  { href: "/buybox",        label: "Buy Box",       icon: Zap },
  { href: "/analytics",     label: "Analytics",     icon: BarChart2 },
  { href: "/alerts",        label: "Alerts",        icon: Bell },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        width: 240,
        minHeight: "100vh",
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        position: "fixed",
        top: 0,
        left: 0,
        bottom: 0,
        zIndex: 50,
      }}
    >
      {/* Logo */}
      <div style={{ padding: "24px 20px 20px", borderBottom: "1px solid var(--border-muted)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Activity size={18} color="#fff" />
          </div>
          <div>
            <p style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1 }}>
              BearingMonitor
            </p>
            <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 3 }}>
              Amazon India Intelligence
            </p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "12px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "9px 12px",
                borderRadius: 8,
                textDecoration: "none",
                fontSize: 13,
                fontWeight: active ? 600 : 400,
                color: active ? "#fff" : "var(--text-secondary)",
                background: active
                  ? "linear-gradient(90deg,rgba(59,130,246,0.22),rgba(139,92,246,0.10))"
                  : "transparent",
                borderLeft: active ? "2px solid #3b82f6" : "2px solid transparent",
                transition: "all 0.15s ease",
              }}
              className={clsx(!active && "nav-item")}
            >
              <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: "14px 16px", borderTop: "1px solid var(--border-muted)" }}>
        <p style={{ fontSize: 10, color: "var(--text-muted)", textAlign: "center" }}>
          © 2026 Nisargasoft · v2.0
        </p>
      </div>

      <style>{`
        .nav-item:hover {
          background: var(--bg-card-hover) !important;
          color: var(--text-primary) !important;
        }
      `}</style>
    </aside>
  );
}
