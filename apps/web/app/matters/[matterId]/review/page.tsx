import { AppShell } from "@/components/shell";
import { ReviewQueue } from "@/components/v3/lists";

export default async function Page({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;
  return (
    <AppShell>
      <ReviewQueue matterId={matterId} />
    </AppShell>
  );
}
