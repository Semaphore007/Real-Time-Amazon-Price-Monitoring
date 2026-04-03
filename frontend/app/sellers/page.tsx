import Shell from "@/components/Shell";
import SellersClient from "./SellersClient";
export const metadata = { title: "Sellers · Bearing Price Monitor" };
export default function SellersPage() {
  return (
    <Shell title="Seller Intelligence" subtitle="Rankings, market share, and performance metrics">
      <SellersClient />
    </Shell>
  );
}
