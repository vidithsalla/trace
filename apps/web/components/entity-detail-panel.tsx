"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type Mention = {
  id: string;
  document_id: string;
  document_name: string;
  chunk_id: string | null;
  page_number: number | null;
  mention_text: string;
  context_text: string | null;
  viewer_url: string | null;
};

type TimelineItem = {
  event_id: string;
  date: string | null;
  date_text: string | null;
  title: string;
  description: string;
  conflict_flag: boolean;
};

type EntityDetail = {
  id: string;
  matter_id: string;
  entity_type: string;
  canonical_name: string;
  aliases_json: string[];
  summary_json: Record<string, unknown>;
  mention_count: number;
  key_documents: { document_id: string; document_name: string; mention_count: number }[];
  mentions: Mention[];
  timeline: TimelineItem[];
};

export function EntityDetailPanel({
  matterId,
  entityId,
}: {
  matterId: string;
  entityId: string;
}) {
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [alias, setAlias] = useState("");
  const [sourceEntityId, setSourceEntityId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    void loadEntity();
  }, [entityId]);

  async function loadEntity() {
    setError(null);
    const response = await fetch(`/api/entities/${entityId}`);
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Trace could not load this entity.");
      return;
    }
    setEntity(await response.json());
  }

  async function addAlias(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!alias.trim()) {
      return;
    }
    setIsSaving(true);
    setError(null);
    const response = await fetch(`/api/entities/${entityId}/aliases`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ alias }),
    });
    setIsSaving(false);
    if (!response.ok) {
      setError("Trace could not add that alias.");
      return;
    }
    setAlias("");
    setEntity(await response.json());
  }

  async function mergeAlias(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sourceEntityId.trim()) {
      return;
    }
    setIsSaving(true);
    setError(null);
    const response = await fetch(`/api/entities/${entityId}/merge`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_entity_id: sourceEntityId }),
    });
    setIsSaving(false);
    if (!response.ok) {
      setError("Trace could not merge that entity. Confirm the source entity ID is in this matter.");
      return;
    }
    setSourceEntityId("");
    setEntity(await response.json());
  }

  if (!entity) {
    return (
      <div className="rounded-3xl border border-[var(--border)] bg-white p-5 text-sm text-neutral-600">
        {error ?? "Loading entity..."}
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
      <section className="space-y-5">
        <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <Link className="text-sm font-semibold text-[var(--accent)]" href={`/matters/${matterId}/entities`}>
            Back to entities
          </Link>
          <p className="mt-5 text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
            {entity.entity_type}
          </p>
          <h3 className="mt-2 text-3xl font-semibold">{entity.canonical_name}</h3>
          <p className="mt-4 text-sm leading-7 text-neutral-700">
            {String(entity.summary_json.overview ?? "No summary generated yet.")}
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <Metric label="Mentions" value={String(entity.mention_count)} />
            <Metric label="Key documents" value={String(entity.key_documents.length)} />
          </div>
        </article>

        <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <p className="font-semibold">Summary profile</p>
          <dl className="mt-4 space-y-4 text-sm leading-6">
            <div>
              <dt className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">Role</dt>
              <dd className="mt-1 text-neutral-700">
                {String(entity.summary_json.role_in_matter ?? "Pending summary.")}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">Key actions</dt>
              <dd className="mt-2 space-y-2 text-neutral-700">
                {asList(entity.summary_json.key_actions).slice(0, 5).map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </dd>
            </div>
          </dl>
        </article>

        <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <p className="font-semibold">Aliases and merge</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[entity.canonical_name, ...entity.aliases_json].map((item) => (
              <span
                key={item}
                className="rounded-md bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]"
              >
                {item}
              </span>
            ))}
          </div>
          <form onSubmit={addAlias} className="mt-5 flex flex-col gap-3 sm:flex-row">
            <input
              className="min-h-11 flex-1 rounded-md border border-[var(--border)] px-4 text-sm"
              placeholder="Add alias, e.g. J. Mercer"
              value={alias}
              onChange={(event) => setAlias(event.target.value)}
            />
            <button
              className="rounded-2xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              disabled={isSaving || !alias.trim()}
              type="submit"
            >
              Add alias
            </button>
          </form>
          <form onSubmit={mergeAlias} className="mt-3 flex flex-col gap-3 sm:flex-row">
            <input
              className="min-h-11 flex-1 rounded-md border border-[var(--border)] px-4 text-sm"
              placeholder="Source entity ID to merge"
              value={sourceEntityId}
              onChange={(event) => setSourceEntityId(event.target.value)}
            />
            <button
              className="rounded-md border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--accent)] disabled:opacity-50"
              disabled={isSaving || !sourceEntityId.trim()}
              type="submit"
            >
              Merge
            </button>
          </form>
          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
        </article>
      </section>

      <section className="space-y-5">
        <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <p className="font-semibold">Traceable mentions</p>
          <div className="mt-4 space-y-3">
            {entity.mentions.map((mention) => (
              <div key={mention.id} className="rounded-2xl bg-[var(--muted)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold">{mention.document_name}</p>
                  <span className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                    Page {mention.page_number ?? "n/a"}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-neutral-700">
                  {mention.context_text ?? mention.mention_text}
                </p>
                {mention.viewer_url ? (
                  <a
                    className="mt-3 inline-flex rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                    href={mention.viewer_url}
                  >
                    Open source
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
          <p className="font-semibold">Entity timeline</p>
          <div className="mt-4 space-y-3">
            {entity.timeline.length === 0 ? (
              <p className="text-sm text-neutral-600">No chronology events reference this entity yet.</p>
            ) : null}
            {entity.timeline.map((item) => (
              <div key={item.event_id} className="rounded-md border border-[var(--border)] p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                  {item.date ?? item.date_text ?? "Undated"}
                </p>
                <p className="mt-2 font-semibold">{item.title}</p>
                <p className="mt-2 text-sm leading-6 text-neutral-700">{item.description}</p>
                {item.conflict_flag ? (
                  <span className="mt-3 inline-flex rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">
                    disputed
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[var(--muted)] p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}
