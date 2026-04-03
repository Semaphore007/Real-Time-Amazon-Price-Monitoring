import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Bearing Price Monitor | Amazon India Intelligence",
  description:
    "Real-time pricing intelligence for SKF bearing distributors on Amazon India. Track sellers, buy-box ownership, price trends and competitive alerts.",
  keywords: ["Amazon India", "SKF bearings", "price monitoring", "seller analytics", "buy box"],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
