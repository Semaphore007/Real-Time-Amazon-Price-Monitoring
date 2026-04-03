import Shell from "@/components/Shell";
import BuyBoxClient from "./BuyBoxClient";
export const metadata = { title: "Buy Box · Bearing Price Monitor" };
export default function BuyBoxPage() {
  return (
    <Shell title="Buy Box Tracker" subtitle="Real-time and historical buy-box ownership by ASIN">
      <BuyBoxClient />
    </Shell>
  );
}
