import { AskPanel } from "@/components/ask-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function AskPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Grounded Q&A" title="Ask the Matter">
        <AskPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
