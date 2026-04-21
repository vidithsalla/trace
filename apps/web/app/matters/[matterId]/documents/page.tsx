import { DocumentUploadPanel } from "@/components/document-upload-panel";
import { AppShell, PageCard } from "@/components/shell";

export default async function DocumentsPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;

  return (
    <AppShell>
      <PageCard eyebrow="Documents" title="Matter Documents">
        <DocumentUploadPanel matterId={matterId} />
      </PageCard>
    </AppShell>
  );
}
