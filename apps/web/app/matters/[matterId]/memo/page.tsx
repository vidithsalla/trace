import { MemoPanel } from "@/components/memo-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function MemoPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Issue Memo" title="First-pass memo builder">
        <MemoPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
