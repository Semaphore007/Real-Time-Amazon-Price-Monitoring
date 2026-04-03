import Shell from "@/components/Shell";
import ProductsClient from "./ProductsClient";

export const metadata = { title: "Products · Bearing Price Monitor" };

export default function ProductsPage() {
  return (
    <Shell title="Products" subtitle="All tracked ASINs with latest pricing">
      <ProductsClient />
    </Shell>
  );
}
