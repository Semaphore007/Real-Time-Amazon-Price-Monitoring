import Shell from "@/components/Shell";
import AnalyticsClient from "./AnalyticsClient";
export const metadata = { title: "Analytics · Bearing Price Monitor" };
export default function AnalyticsPage() {
  return (
    <Shell title="Deep Analytics" subtitle="Price heatmaps, undercutting patterns and market intelligence">
      <AnalyticsClient />
    </Shell>
  );
}
