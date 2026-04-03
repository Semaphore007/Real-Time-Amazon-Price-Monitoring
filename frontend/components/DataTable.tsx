"use client";
import React from "react";

interface Column<T> {
  key: keyof T | string;
  header: string;
  render?: (row: T) => React.ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  emptyText?: string;
  maxHeight?: number;
}

export default function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  emptyText = "No data available",
  maxHeight = 400,
}: DataTableProps<T>) {
  return (
    <div style={{ overflowX: "auto", overflowY: "auto", maxHeight, borderRadius: 8, border: "1px solid var(--border-muted)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "var(--bg-surface)", position: "sticky", top: 0, zIndex: 2 }}>
            {columns.map(col => (
              <th
                key={String(col.key)}
                style={{
                  padding: "10px 14px",
                  textAlign: "left",
                  color: "var(--text-muted)",
                  fontWeight: 600,
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  whiteSpace: "nowrap",
                  borderBottom: "1px solid var(--border)",
                  width: col.width,
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}
              >
                {emptyText}
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={i}
                style={{
                  background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                  transition: "background 0.12s",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-card-hover)")}
                onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)")}
              >
                {columns.map(col => (
                  <td
                    key={String(col.key)}
                    style={{
                      padding: "9px 14px",
                      color: "var(--text-primary)",
                      borderBottom: "1px solid var(--border-muted)",
                      whiteSpace: "nowrap",
                      maxWidth: 260,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {col.render ? col.render(row) : String(row[col.key as keyof T] ?? "—")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
