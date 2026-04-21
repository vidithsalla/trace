"use client";

import Link from "next/link";
import { ChangeEvent, useEffect, useState } from "react";

type DocumentItem = {
  id: string;
  file_name: string;
  display_name?: string | null;
  mime_type: string;
  file_size_bytes: number;
  parse_status: string;
  ocr_status: string;
  ingest_status: string;
  error_message?: string | null;
  created_at: string;
};

export function DocumentUploadPanel({ matterId }: { matterId: string }) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);

  async function loadDocuments() {
    const response = await fetch(`/api/matters/${matterId}/documents`, { cache: "no-store" });
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Unable to load documents.");
      setIsLoading(false);
      return;
    }
    setDocuments(await response.json());
    setIsLoading(false);
  }

  useEffect(() => {
    let isMounted = true;
    loadDocuments().catch(() => {
      if (isMounted) {
        setError("Unable to load documents.");
        setIsLoading(false);
      }
    });

    const interval = window.setInterval(() => {
      loadDocuments().catch(() => undefined);
    }, 3000);

    return () => {
      isMounted = false;
      window.clearInterval(interval);
    };
  }, [matterId]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setError(null);
    setIsUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`/api/matters/${matterId}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    setIsUploading(false);
    event.target.value = "";

    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: "Upload failed." }));
      setError(typeof body.detail === "string" ? body.detail : "Upload failed.");
      return;
    }

    await loadDocuments();
  }

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold">Upload source document</p>
            <p className="mt-1 text-sm text-neutral-600">
              Supported now: PDF, DOCX, TXT, CSV, XLSX, JPG, and PNG.
            </p>
          </div>
          <label className="cursor-pointer rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-medium text-white">
            {isUploading ? "Uploading..." : "Choose file"}
            <input
              className="sr-only"
              type="file"
              onChange={handleUpload}
              disabled={isUploading}
              accept=".pdf,.docx,.txt,.csv,.xlsx,.jpg,.jpeg,.png"
            />
          </label>
        </div>
        {error ? (
          <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <div className="h-40 animate-pulse rounded-3xl border border-[var(--border)] bg-[var(--panel)]" />
      ) : (
        <div className="space-y-3">
          {documents.length === 0 ? (
            <p className="rounded-2xl border border-[var(--border)] px-4 py-3 text-sm text-neutral-600">
              No documents uploaded yet.
            </p>
          ) : null}
          {documents.map((document) => (
            <div
              key={document.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[var(--border)] px-4 py-3"
            >
              <div>
                <p className="font-medium">{document.display_name ?? document.file_name}</p>
                <p className="text-sm text-neutral-600">
                  {formatBytes(document.file_size_bytes)} · {document.mime_type}
                </p>
                <Link
                  className="mt-2 inline-block text-sm font-semibold text-[var(--accent)]"
                  href={`/matters/${matterId}/documents/${document.id}?page=1`}
                >
                  Open viewer
                </Link>
                {document.error_message ? (
                  <p className="mt-1 text-sm text-red-700">{document.error_message}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
                <StatusBadge label="Ingest" value={document.ingest_status} />
                <StatusBadge label="Parse" value={document.parse_status} />
                <StatusBadge label="OCR" value={document.ocr_status} />
              </div>
            </div>
          ))}
        </div>
      )}
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

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
