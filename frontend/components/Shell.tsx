"use client";
import React from "react";
import Sidebar from "@/components/Sidebar";
import { RefreshCw } from "lucide-react";

interface ShellProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export default function Shell({ title, subtitle, children, action }: ShellProps) {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
      <Sidebar />
      <div style={{ marginLeft: 240, flex: 1, display: "flex", flexDirection: "column", minHeight: "100vh" }}>
        {/* Top bar */}
        <header
          style={{
            position: "sticky",
            top: 0,
            zIndex: 40,
            background: "rgba(10,13,20,0.85)",
            backdropFilter: "blur(12px)",
            borderBottom: "1px solid var(--border)",
            padding: "0 28px",
            height: 60,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h1 style={{ fontSize: 17, fontWeight: 700, color: "var(--text-primary)" }}>{title}</h1>
            {subtitle && <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>{subtitle}</p>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {action}
            <div
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 10px", borderRadius: 8,
                background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.25)",
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
              <span style={{ fontSize: 11, color: "#10b981", fontWeight: 600 }}>Live</span>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main style={{ flex: 1, padding: "24px 28px", maxWidth: 1600 }}>{children}</main>

        <footer style={{ padding: "14px 28px", borderTop: "1px solid var(--border-muted)" }}>
          <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
            Amazon India Bearing Market Intelligence · Nisargasoft Hackathon 2026
          </p>
        </footer>
      </div>
    </div>
  );
}
