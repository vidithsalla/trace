import { AppShell } from "@/components/shell";
import { Investigate } from "@/components/v3/investigate";

export default async function Page({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;
  return (
    <AppShell>
      <Investigate matterId={matterId} />
    </AppShell>
  );
}
