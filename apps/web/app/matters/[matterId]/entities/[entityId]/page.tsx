import { EntityDetailPanel } from "@/components/entity-detail-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function EntityDetailPage({
  params,
}: {
  params: Promise<{ matterId: string; entityId: string }>;
}) {
  const { matterId, entityId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Entity" title="Evidence-backed profile">
        <EntityDetailPanel matterId={matterId} entityId={entityId} />
      </PageCard>
    </AppShell>
  );
}
