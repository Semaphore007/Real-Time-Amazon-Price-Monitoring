import Shell from "@/components/Shell";
import PricesClient from "./PricesClient";

export const metadata = { title: "Price Trends · Bearing Price Monitor" };

export default function PricesPage() {
  return (
    <Shell title="Price Trends" subtitle="Historical price analysis per product and seller">
      <PricesClient />
    </Shell>
  );
}
