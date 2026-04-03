// Central API client — all fetch calls go through here

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Product {
  asin: string;
  title: string;
  brand: string | null;
  category: string | null;
  updated_at: string | null;
}

export interface ProductDetail extends Product {
  latest_price: number | null;
  buy_box_events: number;
}

export interface PricePoint {
  asin: string;
  seller_name: string | null;
  location: string | null;
  price: number | null;
  availability: string | null;
  captured_at: string;
}

export interface Seller {
  seller_name: string;
  rating: number | null;
  fulfillment_type: string | null;
}

export interface SellerRanking {
  seller_name: string;
  buy_box_win_rate_pct: number;
  market_share_pct: number;
}

export interface BuyBoxEvent {
  asin: string;
  seller_name: string;
  location: string | null;
  price: number | null;
  captured_at: string;
}

export interface Offer {
  asin: string;
  title: string;
  seller_name: string;
  location: string | null;
  offer_price: number | null;
  is_buy_box: boolean;
  is_fba: boolean;
  availability: string | null;
  captured_at: string;
}

export interface Alert {
  alert_type: string;
  asin: string;
  seller_name: string | null;
  location: string | null;
  severity: string;
  message: string;
  created_at: string;
}

export interface AnalyticsSummary {
  price_points: number;
  products_tracked: number;
  average_market_price: number | null;
  min_price_seller: { seller_name: string; offer_price: number; asin: string } | null;
  frequent_price_changers: { seller_name: string; changes: number }[];
  buy_box_win_rate: { seller_name: string; win_rate_pct: number }[];
  undercutting_events: { asin: string; seller_name: string; price: number; undercut_pct: number }[];
  seller_market_share: { seller_name: string; market_share_pct: number }[];
}

export interface PriceTrend {
  asin: string;
  trends: { date: string; seller_name: string; price: number }[];
  overall_min: number;
  overall_max: number;
  overall_avg: number;
}

export interface BuyBoxOwnership {
  asin: string;
  seller_name: string;
  events: number;
  total: number;
  ownership_pct: number;
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  products:       ()         => get<Product[]>("/products"),
  product:        (asin: string) => get<ProductDetail>(`/product/${asin}`),
  priceHistory:   (asin: string, loc?: string) =>
    get<PricePoint[]>(`/price-history/${asin}${loc ? `?location=${loc}` : ""}`),
  sellers:        ()         => get<Seller[]>("/sellers"),
  sellerRanking:  ()         => get<SellerRanking[]>("/sellers/ranking"),
  buyBoxHistory:  (asin: string) => get<BuyBoxEvent[]>(`/buy-box-history/${asin}`),
  buyBoxCurrent:  ()         => get<BuyBoxEvent[]>("/buy-box/current"),
  offers:         (asin: string, loc?: string) =>
    get<Offer[]>(`/offers/${asin}${loc ? `?location=${loc}` : ""}`),
  marketSnapshot: ()         => get<Offer[]>("/market/snapshot"),
  alerts:         (limit = 100) => get<Alert[]>(`/alerts?limit=${limit}`),
  summary:        (asin?: string) =>
    get<AnalyticsSummary>(`/analytics/summary${asin ? `?asin=${asin}` : ""}`),
  priceTrends:    (asin: string) => get<PriceTrend>(`/analytics/price-trends/${asin}`),
  undercutting:   ()         => get<AnalyticsSummary["undercutting_events"]>("/analytics/undercutting"),
  buyBoxOwnership: ()        => get<BuyBoxOwnership[]>("/analytics/buy-box-ownership"),
  heatmap:        (asin?: string) =>
    get<Record<string, number | string | null>[]>(`/analytics/heatmap${asin ? `?asin=${asin}` : ""}`),
  health:         ()         => get<{ status: string }>("/health"),
};

export const WS_URL = (BASE.replace(/^http/, "ws")) + "/ws/alerts";
