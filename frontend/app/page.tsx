import Shell from "@/components/Shell";
import OverviewClient from "./OverviewClient";

export const metadata = {
  title: "Overview · Bearing Price Monitor",
};

export default function OverviewPage() {
  return (
    <Shell
      title="Market Overview"
      subtitle="Amazon India · SKF Bearings · Real-time intelligence"
    >
      <OverviewClient />
    </Shell>
  );
}
