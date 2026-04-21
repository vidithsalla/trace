import { ContradictionsPanel } from "@/components/contradictions-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function ContradictionsPage({
  params,
}: {
  params: Promise<{ matterId: string }>;
}) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Contradictions" title="Side-by-side evidence review">
        <ContradictionsPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
