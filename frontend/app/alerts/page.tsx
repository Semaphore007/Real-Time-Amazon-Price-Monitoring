import Shell from "@/components/Shell";
import AlertsClient from "./AlertsClient";
export const metadata = { title: "Alerts · Bearing Price Monitor" };
export default function AlertsPage() {
  return (
    <Shell title="Alert Center" subtitle="Price drops, buy-box changes, and competitor events">
      <AlertsClient />
    </Shell>
  );
}
