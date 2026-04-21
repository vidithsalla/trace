import { AuditTrail } from "@/components/audit-trail";
import { AppShell, PageCard } from "@/components/shell";

export default async function SettingsPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;
  return (
    <AppShell>
      <PageCard eyebrow="Admin" title="Trace settings and audit posture">
        <div className="space-y-8">
          <ul className="space-y-3 text-sm text-neutral-700">
            <li>Role management and matter membership</li>
            <li>Model endpoint and deployment configuration</li>
            <li>Retention settings and audit export entry points</li>
            <li>OCR and inference limits</li>
          </ul>
          <AuditTrail matterId={matterId} />
        </div>
      </PageCard>
    </AppShell>
  );
}
