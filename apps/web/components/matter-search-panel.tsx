"use client";

import { FormEvent, useState } from "react";

type SearchResult = {
  chunk_id: string | null;
  document_id: string;
  document_name: string;
  page_number: number | null;
  snippet: string;
  score: number;
  metadata: Record<string, unknown>;
};

type SearchResponse = {
  query: string;
  total: number;
  results: SearchResult[];
};

export function MatterSearchPanel({ matterId }: { matterId: string }) {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }

    setError(null);
    setIsSearching(true);
    const searchResponse = await fetch(`/api/matters/${matterId}/search`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, limit: 8 }),
    });
    setIsSearching(false);

    if (searchResponse.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!searchResponse.ok) {
      setError("Search failed. Try again after ingestion finishes.");
      return;
    }
    setResponse(await searchResponse.json());
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSubmit}
        className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5"
      >
        <label className="text-sm font-semibold" htmlFor="matter-search">
          Search the matter corpus
        </label>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <input
            id="matter-search"
            className="min-h-12 flex-1 rounded-md border border-[var(--border)] bg-white px-4 text-sm outline-none focus:border-[var(--accent)]"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Try: defect knowledge before shipment"
          />
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="rounded-2xl bg-[var(--accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {isSearching ? "Searching..." : "Search"}
          </button>
        </div>
        <p className="mt-3 text-xs text-neutral-600">
          Results are matter-scoped and ranked with lexical plus lightweight local vector signals.
        </p>
        {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      </form>

      {response ? (
        <div className="space-y-3">
          <p className="text-sm text-neutral-600">
            {response.total} result{response.total === 1 ? "" : "s"} for “{response.query}”
          </p>
          {response.results.map((result) => (
            <article
              key={result.chunk_id ?? `${result.document_id}-${result.page_number}`}
              className="rounded-3xl border border-[var(--border)] bg-white p-5"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold">{result.document_name}</h3>
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
                    Page {result.page_number ?? "n/a"} · score {result.score.toFixed(4)}
                  </p>
                </div>
                <span className="rounded-md bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
                  Chunk
                </span>
              </div>
              <p className="mt-4 text-sm leading-7 text-neutral-700">{result.snippet}</p>
              <a
                className="mt-4 inline-flex rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                href={viewerHref(matterId, result)}
              >
                Open source page
              </a>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function viewerHref(matterId: string, result: SearchResult) {
  const params = new URLSearchParams();
  params.set("page", String(result.page_number ?? 1));
  params.set("quote", result.snippet);
  if (result.chunk_id) {
    params.set("chunk", result.chunk_id);
  }
  return `/matters/${matterId}/documents/${result.document_id}?${params.toString()}`;
}
