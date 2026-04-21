import { ChronologyPanel } from "@/components/chronology-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function ChronologyPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Chronology" title="Citation-backed timeline">
        <ChronologyPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
