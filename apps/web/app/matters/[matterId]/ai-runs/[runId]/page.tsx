import { AIRunDetail } from "@/components/ai-run-detail";
import { AppShell, PageCard } from "@/components/shell";

export default async function AIRunPage({
  params,
}: {
  params: Promise<{ matterId: string; runId: string }>;
}) {
  const { runId } = await params;
  return (
    <AppShell>
      <PageCard eyebrow="AI Run" title="Workflow audit detail">
        <AIRunDetail runId={runId} />
      </PageCard>
    </AppShell>
  );
}
