import { DocumentViewer } from "@/components/document-viewer";
import { AppShell, PageCard } from "@/components/shell";

export default async function DocumentViewerPage({
  params,
  searchParams,
}: {
  params: Promise<{ matterId: string; documentId: string }>;
  searchParams: Promise<{ page?: string; quote?: string; chunk?: string }>;
}) {
  const { matterId, documentId } = await params;
  const { page, quote, chunk } = await searchParams;
  const initialPage = Math.max(Number(page ?? "1") || 1, 1);

  return (
    <AppShell>
      <PageCard eyebrow="Source Viewer" title="Evidence Trust Loop">
        <DocumentViewer
          matterId={matterId}
          documentId={documentId}
          initialPage={initialPage}
          quote={quote}
          chunkId={chunk}
        />
      </PageCard>
    </AppShell>
  );
}
