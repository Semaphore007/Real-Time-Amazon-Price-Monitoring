"use client";
import React from "react";

interface CardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  noPadding?: boolean;
  className?: string;
}

export default function Card({ title, subtitle, children, action, noPadding }: CardProps) {
  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        overflow: "hidden",
      }}
    >
      {(title || action) && (
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border-muted)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            {title && (
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                {title}
              </h3>
            )}
            {subtitle && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{subtitle}</p>
            )}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      <div style={noPadding ? {} : { padding: "16px 20px" }}>{children}</div>
    </div>
  );
}
