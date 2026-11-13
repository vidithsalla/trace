import { AppShell } from "@/components/shell";
import { Packets } from "@/components/v3/lists";

export default async function Page({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;
  return (
    <AppShell>
      <Packets matterId={matterId} />
    </AppShell>
  );
}
