import { AppShell } from "@/components/shell";
import { ClaimInspector } from "@/components/v3/claim-inspector";

export default async function ClaimPage({
  params,
  searchParams,
}: {
  params: Promise<{ matterId: string; claimId: string }>;
  searchParams: Promise<{ revision?: string }>;
}) {
  const { matterId, claimId } = await params;
  const { revision } = await searchParams;
  const parsed = revision ? Number.parseInt(revision, 10) : undefined;
  return (
    <AppShell>
      <ClaimInspector key={`${claimId}-${parsed ?? "current"}`} matterId={matterId} claimId={claimId} revision={Number.isFinite(parsed) ? parsed : undefined} />
    </AppShell>
  );
}
