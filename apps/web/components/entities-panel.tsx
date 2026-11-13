"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type KeyDocument = {
  document_id: string;
  document_name: string;
  mention_count: number;
};

type EntityListItem = {
  id: string;
  matter_id: string;
  entity_type: string;
  canonical_name: string;
  aliases_json: string[];
  summary_json: Record<string, unknown>;
  mention_count: number;
  key_documents: KeyDocument[];
  last_seen_at: string | null;
};

const REQUIRED_ENTITIES = [
  "Jane Mercer",
  "Northshore Supply",
  "Priya Shah",
  "Project Falcon",
  "Compressor Unit 7A",
];

export function EntitiesPanel({ matterId }: { matterId: string }) {
  const [entities, setEntities] = useState<EntityListItem[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);

  useEffect(() => {
    void loadEntities();
  }, [matterId]);

  async function loadEntities() {
    setIsLoading(true);
    setError(null);
    const response = await fetch(`/api/matters/${matterId}/entities`);
    setIsLoading(false);
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Trace could not load entities for this matter.");
      return;
    }
    setEntities(await response.json());
  }

  async function extractEntities() {
    setIsExtracting(true);
    setError(null);
    const response = await fetch(`/api/matters/${matterId}/entities/extract`, {
      method: "POST",
      headers: { "content-type": "application/json" },
    });
    setIsExtracting(false);
    if (!response.ok) {
      setError("Trace could not extract entities from the parsed matter text.");
      return;
    }
    setEntities(await response.json());
  }

  const visibleEntities = entities.filter((entity) => {
    const haystack = [
      entity.canonical_name,
      entity.entity_type,
      entity.aliases_json.join(" "),
      entity.key_documents.map((document) => document.document_name).join(" "),
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query.toLowerCase().trim());
  });

  const coveredNames = REQUIRED_ENTITIES.filter((name) =>
    entities.some((entity) =>
      [entity.canonical_name, ...entity.aliases_json].some((candidate) =>
        candidate.toLowerCase().includes(name.toLowerCase()) ||
        name.toLowerCase().includes(candidate.toLowerCase()),
      ),
    ),
  );

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-[var(--border)] bg-white p-5">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
              Evidence-backed profiles
            </p>
            <h3 className="mt-2 text-xl font-semibold">Matter entities and witnesses</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-700">
              Trace harvests canonical entities deterministically from parsed chunks, then uses
              local mock synthesis only to summarize validated mentions.
            </p>
          </div>
          <button
            className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
            disabled={isExtracting}
            onClick={extractEntities}
            type="button"
          >
            {isExtracting ? "Extracting..." : "Extract entities"}
          </button>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
          <input
            className="rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
            placeholder="Filter by person, organization, project, document..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="rounded-md border border-[var(--border)] px-3 py-2 text-sm text-neutral-700">
            {isLoading ? "Loading..." : `${visibleEntities.length} visible entities`}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {REQUIRED_ENTITIES.map((name) => (
            <span
              key={name}
              className={
                coveredNames.includes(name)
                  ? "rounded-md bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800"
                  : "rounded-md bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800"
              }
            >
              {name}
            </span>
          ))}
        </div>
        {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visibleEntities.map((entity) => (
          <article
            key={entity.id}
            className="rounded-3xl border border-[var(--border)] bg-white p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                  {entity.entity_type}
                </p>
                <h3 className="mt-2 text-xl font-semibold">{entity.canonical_name}</h3>
              </div>
              <span className="rounded-md bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
                {entity.mention_count} mentions
              </span>
            </div>
            <p className="mt-4 line-clamp-3 text-sm leading-6 text-neutral-700">
              {String(entity.summary_json.overview ?? "No summary generated yet.")}
            </p>
            {entity.aliases_json.length > 0 ? (
              <p className="mt-3 text-xs text-neutral-600">
                Aliases: {entity.aliases_json.join(", ")}
              </p>
            ) : null}
            <div className="mt-4 space-y-2">
              {entity.key_documents.slice(0, 3).map((document) => (
                <p key={document.document_id} className="text-xs text-neutral-600">
                  {document.document_name} · {document.mention_count} mention
                  {document.mention_count === 1 ? "" : "s"}
                </p>
              ))}
            </div>
            <Link
              className="mt-5 inline-flex rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
              href={`/matters/${matterId}/entities/${entity.id}`}
            >
              Open entity page
            </Link>
          </article>
        ))}
        {visibleEntities.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-[var(--border)] p-6 text-sm leading-7 text-neutral-600">
            No entities are available yet. Run extraction after documents have been parsed.
          </div>
        ) : null}
      </section>
    </div>
  );
}
