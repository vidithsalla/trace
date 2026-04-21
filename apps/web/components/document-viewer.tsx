"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type DocumentDetail = {
  id: string;
  matter_id: string;
  file_name: string;
  display_name?: string | null;
  mime_type: string;
  page_count: number | null;
  parse_status: string;
  ocr_status: string;
  ingest_status: string;
  extraction_quality_score: number | null;
  error_message?: string | null;
};

type DocumentPage = {
  id: string;
  document_id: string;
  page_number: number;
  raw_text: string | null;
  normalized_text: string | null;
  image_storage_key: string | null;
  ocr_confidence: number | null;
  has_text_layer: boolean;
  metadata_json: Record<string, unknown>;
};

export function DocumentViewer({
  matterId,
  documentId,
  initialPage,
  quote,
  chunkId,
}: {
  matterId: string;
  documentId: string;
  initialPage: number;
  quote?: string;
  chunkId?: string;
}) {
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [page, setPage] = useState<DocumentPage | null>(null);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const sourceUrl = `/api/documents/${documentId}/file`;
  const pdfUrl = `${sourceUrl}#page=${pageNumber}`;
  const maxPage = Math.max(document?.page_count ?? 1, 1);
  const normalizedQuote = useMemo(() => cleanQuote(quote), [quote]);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setIsLoading(true);
      setError(null);
      const [documentResponse, pageResponse] = await Promise.all([
        fetch(`/api/documents/${documentId}`, { cache: "no-store" }),
        fetch(`/api/documents/${documentId}/pages/${pageNumber}`, { cache: "no-store" }),
      ]);

      if (documentResponse.status === 401 || pageResponse.status === 401) {
        window.location.assign("/sign-in");
        return;
      }
      if (!documentResponse.ok) {
        setError("Document not found or not available to this matter.");
        setIsLoading(false);
        return;
      }
      if (!pageResponse.ok) {
        setDocument(await documentResponse.json());
        setPage(null);
        setError("Page not found for this document.");
        setIsLoading(false);
        return;
      }

      if (isMounted) {
        setDocument(await documentResponse.json());
        setPage(await pageResponse.json());
        setIsLoading(false);
      }
    }

    load().catch(() => {
      if (isMounted) {
        setError("Unable to load the document viewer.");
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [documentId, pageNumber]);

  function jumpToPage(nextPage: number) {
    const bounded = Math.min(Math.max(nextPage, 1), maxPage);
    setPageNumber(bounded);
    const params = new URLSearchParams();
    params.set("page", String(bounded));
    if (quote) {
      params.set("quote", quote);
    }
    if (chunkId) {
      params.set("chunk", chunkId);
    }
    window.history.replaceState(null, "", `?${params.toString()}`);
  }

  if (isLoading && !document) {
    return <div className="h-80 animate-pulse rounded-3xl bg-[var(--muted)]" />;
  }

  if (error && !document) {
    return <ViewerError message={error} matterId={matterId} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link className="text-sm font-semibold text-[var(--accent)]" href={`/matters/${matterId}/documents`}>
            Back to documents
          </Link>
          <h2 className="mt-3 text-3xl font-semibold">
            {document?.display_name ?? document?.file_name ?? "Document"}
          </h2>
          <p className="mt-2 text-sm text-neutral-600">
            Page {pageNumber} of {maxPage} · {document?.mime_type}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
          <StatusBadge label="Ingest" value={document?.ingest_status ?? "unknown"} />
          <StatusBadge label="Parse" value={document?.parse_status ?? "unknown"} />
          <StatusBadge label="OCR" value={document?.ocr_status ?? "unknown"} />
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-4">
        <button
          className="rounded-full border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-40"
          disabled={pageNumber <= 1}
          onClick={() => jumpToPage(pageNumber - 1)}
        >
          Previous
        </button>
        <label className="flex items-center gap-2 text-sm">
          Jump to page
          <input
            className="w-20 rounded-xl border border-[var(--border)] bg-white px-3 py-2"
            type="number"
            min={1}
            max={maxPage}
            value={pageNumber}
            onChange={(event) => jumpToPage(Number(event.target.value || 1))}
          />
        </label>
        <button
          className="rounded-full border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-40"
          disabled={pageNumber >= maxPage}
          onClick={() => jumpToPage(pageNumber + 1)}
        >
          Next
        </button>
        <a
          className="ml-auto rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
        >
          Open source
        </a>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-3xl border border-[var(--border)] bg-white p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="font-semibold">Original source</h3>
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
              Preview
            </span>
          </div>
          <SourcePreview document={document} pdfUrl={pdfUrl} sourceUrl={sourceUrl} />
        </section>

        <section className="rounded-3xl border border-[var(--border)] bg-white p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="font-semibold">Extracted text</h3>
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
              {page?.has_text_layer ? "Text layer" : "OCR/fallback"}
            </span>
          </div>
          {normalizedQuote ? (
            <div className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--accent-soft)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
                Citation context{chunkId ? ` · ${chunkId.slice(0, 8)}` : ""}
              </p>
              <p className="mt-2 text-sm leading-6 text-neutral-700">{normalizedQuote}</p>
            </div>
          ) : null}
          <div className="max-h-[640px] overflow-auto rounded-2xl bg-[var(--muted)] p-4 text-sm leading-7 text-neutral-800">
            {page?.normalized_text ? (
              <HighlightedText text={page.normalized_text} query={normalizedQuote} />
            ) : (
              <p className="text-neutral-600">
                No extracted text is available for this page yet. If this is a scan or image,
                enable the OCR provider/add-on and re-run ingestion.
              </p>
            )}
          </div>
          <dl className="mt-4 grid gap-3 text-xs text-neutral-600 sm:grid-cols-2">
            <Metadata label="OCR confidence" value={page?.ocr_confidence ?? "n/a"} />
            <Metadata label="Quality score" value={document?.extraction_quality_score ?? "n/a"} />
            <Metadata label="Page record" value={page?.id.slice(0, 8) ?? "n/a"} />
            <Metadata label="Document" value={documentId.slice(0, 8)} />
          </dl>
        </section>
      </div>
    </div>
  );
}

function SourcePreview({
  document,
  pdfUrl,
  sourceUrl,
}: {
  document: DocumentDetail | null;
  pdfUrl: string;
  sourceUrl: string;
}) {
  if (!document) {
    return <div className="h-[620px] rounded-2xl bg-[var(--muted)]" />;
  }
  if (document.mime_type === "application/pdf") {
    return (
      <iframe
        className="h-[680px] w-full rounded-2xl border border-[var(--border)] bg-[var(--muted)]"
        src={pdfUrl}
        title={document.display_name ?? document.file_name}
      />
    );
  }
  if (document.mime_type.startsWith("image/")) {
    return (
      <div className="flex min-h-[520px] items-center justify-center rounded-2xl bg-[var(--muted)] p-4">
        <img
          className="max-h-[680px] max-w-full rounded-xl object-contain"
          src={sourceUrl}
          alt={document.display_name ?? document.file_name}
        />
      </div>
    );
  }
  if (document.mime_type.startsWith("text/")) {
    return (
      <iframe
        className="h-[680px] w-full rounded-2xl border border-[var(--border)] bg-[var(--muted)]"
        src={sourceUrl}
        title={document.display_name ?? document.file_name}
      />
    );
  }
  return (
    <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--muted)] p-6 text-sm leading-7 text-neutral-700">
      Source preview is not available for this file type yet. Use “Open source” to inspect the
      original alongside the extracted text.
    </div>
  );
}

function HighlightedText({ text, query }: { text: string; query?: string }) {
  const normalized = cleanQuote(query);
  if (!normalized) {
    return <p className="whitespace-pre-wrap">{text}</p>;
  }
  const terms = normalized
    .replace(/[.…”“"]/g, " ")
    .split(/\s+/)
    .filter((term) => term.length > 3)
    .slice(0, 8);
  if (terms.length === 0) {
    return <p className="whitespace-pre-wrap">{text}</p>;
  }
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <p className="whitespace-pre-wrap">
      {parts.map((part, index) =>
        terms.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
          <mark key={`${part}-${index}`} className="rounded bg-yellow-200 px-1">
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        ),
      )}
    </p>
  );
}

function ViewerError({ message, matterId }: { message: string; matterId: string }) {
  return (
    <div className="rounded-3xl border border-red-200 bg-red-50 p-6 text-red-800">
      <p className="font-semibold">{message}</p>
      <Link className="mt-4 inline-block text-sm font-semibold underline" href={`/matters/${matterId}/documents`}>
        Back to documents
      </Link>
    </div>
  );
}

function StatusBadge({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[var(--accent)]">
      {label}: {value}
    </span>
  );
}

function Metadata({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-[var(--muted)] px-3 py-2">
      <dt className="font-semibold text-neutral-800">{label}</dt>
      <dd className="mt-1 break-all">{String(value)}</dd>
    </div>
  );
}

function cleanQuote(value?: string) {
  return value?.replace(/^\.{3}/, "").replace(/\.{3}$/, "").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
