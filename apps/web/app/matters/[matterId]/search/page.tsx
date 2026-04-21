import { MatterSearchPanel } from "@/components/matter-search-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function SearchPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Search" title="Search Corpus">
        <MatterSearchPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
