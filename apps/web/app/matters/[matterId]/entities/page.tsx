import { EntitiesPanel } from "@/components/entities-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function EntitiesPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Entities" title="Witnesses and organizations">
        <EntitiesPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
