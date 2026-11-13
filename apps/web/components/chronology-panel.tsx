"use client";

import { FormEvent, useEffect, useState } from "react";

type Citation = {
  id: string | null;
  document_id: string;
  document_name: string;
  page: number | null;
  chunk_id: string | null;
  quote: string;
  viewer_url: string | null;
  validation_status: string | null;
};

type ChronologyEvent = {
  id: string | null;
  date: string | null;
  date_text: string | null;
  date_confidence: string;
  title: string;
  description: string;
  entity_names: string[];
  citations: Citation[];
  conflict_flag: boolean;
  confidence: string;
  source_type: string;
};

type ChronologyResponse = {
  events: ChronologyEvent[];
  unresolved_ambiguities: string[];
  ai_run_id: string | null;
};

const DEFAULT_TOPIC = "notice, payment approval, defect knowledge, and Project Falcon";

export function ChronologyPanel({ matterId }: { matterId: string }) {
  const [topic, setTopic] = useState(DEFAULT_TOPIC);
  const [entityFilter, setEntityFilter] = useState("");
  const [conflictOnly, setConflictOnly] = useState(false);
  const [events, setEvents] = useState<ChronologyEvent[]>([]);
  const [ambiguities, setAmbiguities] = useState<string[]>([]);
  const [aiRunId, setAiRunId] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ChronologyEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    void loadExistingEvents();
  }, [matterId]);

  async function loadExistingEvents() {
    setIsLoading(true);
    setError(null);
    const response = await fetch(`/api/matters/${matterId}/chronology/events`);
    setIsLoading(false);
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Trace could not load the saved chronology.");
      return;
    }
    setEvents(await response.json());
  }

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsGenerating(true);
    const response = await fetch(`/api/matters/${matterId}/chronology`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic, entity_name: entityFilter || null, limit: 20 }),
    });
    setIsGenerating(false);
    if (response.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!response.ok) {
      setError("Trace could not generate a chronology from the current matter evidence.");
      return;
    }
    const body = (await response.json()) as ChronologyResponse;
    setEvents(body.events);
    setAmbiguities(body.unresolved_ambiguities);
    setAiRunId(body.ai_run_id);
    setSelectedEvent(body.events[0] ?? null);
  }

  async function saveSelectedEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedEvent?.id) {
      return;
    }
    setIsSaving(true);
    setError(null);
    const response = await fetch(`/api/events/${selectedEvent.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        date: selectedEvent.date,
        date_text: selectedEvent.date_text,
        date_confidence: selectedEvent.date_confidence,
        title: selectedEvent.title,
        description: selectedEvent.description,
        entity_names: selectedEvent.entity_names,
        conflict_flag: selectedEvent.conflict_flag,
        confidence: selectedEvent.confidence,
      }),
    });
    setIsSaving(false);
    if (!response.ok) {
      setError("Trace could not save the event edit.");
      return;
    }
    const updated = (await response.json()) as ChronologyEvent;
    setSelectedEvent(updated);
    setEvents((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  const visibleEvents = events
    .filter((event) => {
      if (conflictOnly && !event.conflict_flag) {
        return false;
      }
      const filter = entityFilter.toLowerCase().trim();
      if (!filter) {
        return true;
      }
      return (
        event.entity_names.some((name) => name.toLowerCase().includes(filter)) ||
        event.title.toLowerCase().includes(filter) ||
        event.description.toLowerCase().includes(filter)
      );
    })
    .sort((a, b) => {
      const left = a.date ?? a.date_text ?? "";
      const right = b.date ?? b.date_text ?? "";
      return sortDirection === "asc" ? left.localeCompare(right) : right.localeCompare(left);
    });

  return (
    <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <section className="space-y-5">
        <form
          onSubmit={handleGenerate}
          className="rounded-3xl border border-[var(--border)] bg-white p-5"
        >
          <label className="text-sm font-semibold" htmlFor="chronology-topic">
            Chronology focus
          </label>
          <textarea
            id="chronology-topic"
            className="mt-3 min-h-24 w-full rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm leading-6 outline-none focus:border-[var(--accent)]"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
          />
          <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
            <input
              className="rounded-md border border-[var(--border)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              value={entityFilter}
              onChange={(event) => setEntityFilter(event.target.value)}
              placeholder="Filter by entity, e.g. Jane Mercer"
            />
            <label className="flex items-center gap-2 rounded-md border border-[var(--border)] px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={conflictOnly}
                onChange={(event) => setConflictOnly(event.target.checked)}
              />
              Disputed only
            </label>
            <button
              className="rounded-md border border-[var(--border)] px-3 py-2 text-sm font-semibold text-[var(--accent)]"
              type="button"
              onClick={() => setSortDirection(sortDirection === "asc" ? "desc" : "asc")}
            >
              Sort {sortDirection === "asc" ? "oldest first" : "newest first"}
            </button>
            <button
              className="rounded-2xl bg-[var(--accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
              disabled={isGenerating || !topic.trim()}
              type="submit"
            >
              {isGenerating ? "Building..." : "Generate chronology"}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-neutral-600">
            <a
              className="rounded-md bg-[var(--accent-soft)] px-3 py-2 font-semibold text-[var(--accent)]"
              href={`/api/matters/${matterId}/chronology/export.csv`}
            >
              Export CSV
            </a>
            <a
              className="rounded-md bg-[var(--accent-soft)] px-3 py-2 font-semibold text-[var(--accent)]"
              href={`/api/matters/${matterId}/chronology/export.docx`}
            >
              Export DOCX
            </a>
            <span>{isLoading ? "Loading saved events..." : `${visibleEvents.length} visible events`}</span>
            {aiRunId ? (
              <a className="font-semibold text-[var(--accent)]" href={`/matters/${matterId}/ai-runs/${aiRunId}`}>
                AI run: {aiRunId}
              </a>
            ) : null}
          </div>
          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
        </form>

        <div className="overflow-hidden rounded-3xl border border-[var(--border)] bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-[var(--muted)]">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Entities</th>
                <th className="px-4 py-3">Cites</th>
              </tr>
            </thead>
            <tbody>
              {visibleEvents.map((event) => (
                <tr
                  key={event.id ?? `${event.title}-${event.date_text}`}
                  className="cursor-pointer border-t border-[var(--border)] hover:bg-[var(--muted)]"
                  onClick={() => setSelectedEvent(event)}
                >
                  <td className="px-4 py-3 align-top">
                    <p className="font-semibold">{event.date ?? event.date_text ?? "Undated"}</p>
                    <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                      {event.date_confidence}
                    </p>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <p className="font-semibold">{event.title}</p>
                    <p className="mt-1 line-clamp-2 text-neutral-700">{event.description}</p>
                    {event.conflict_flag ? (
                      <span className="mt-2 inline-flex rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">
                        disputed
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top text-neutral-700">
                    {event.entity_names.length ? event.entity_names.join(", ") : "Unassigned"}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="rounded-md bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
                      {event.citations.length}
                    </span>
                  </td>
                </tr>
              ))}
              {visibleEvents.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-sm text-neutral-600" colSpan={4}>
                    No chronology events yet. Generate from the current matter evidence to begin.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {ambiguities.length > 0 ? (
          <div className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5">
            <p className="font-semibold">Unresolved ambiguities</p>
            <ul className="mt-3 space-y-2 text-sm text-neutral-700">
              {ambiguities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="rounded-3xl border border-[var(--border)] bg-white p-5">
        {selectedEvent ? (
          <EventDetail
            event={selectedEvent}
            isSaving={isSaving}
            onChange={setSelectedEvent}
            onSubmit={saveSelectedEvent}
          />
        ) : (
          <div className="text-sm leading-7 text-neutral-600">
            Select an event to inspect source citations, adjust the date/title/description, or mark
            the item as disputed.
          </div>
        )}
      </section>
    </div>
  );
}

function EventDetail({
  event,
  isSaving,
  onChange,
  onSubmit,
}: {
  event: ChronologyEvent;
  isSaving: boolean;
  onChange: (event: ChronologyEvent) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">Event detail</p>
        <h3 className="mt-2 text-xl font-semibold">{event.title}</h3>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">
          Date
          <input
            className="mt-2 w-full rounded-md border border-[var(--border)] px-3 py-2 text-sm"
            type="date"
            value={event.date ?? ""}
            onChange={(item) => onChange({ ...event, date: item.target.value || null })}
          />
        </label>
        <label className="text-sm font-semibold">
          Date confidence
          <select
            className="mt-2 w-full rounded-md border border-[var(--border)] px-3 py-2 text-sm"
            value={event.date_confidence}
            onChange={(item) => onChange({ ...event, date_confidence: item.target.value })}
          >
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>
      </div>
      <label className="block text-sm font-semibold">
        Title
        <input
          className="mt-2 w-full rounded-md border border-[var(--border)] px-3 py-2 text-sm"
          value={event.title}
          onChange={(item) => onChange({ ...event, title: item.target.value })}
        />
      </label>
      <label className="block text-sm font-semibold">
        Description
        <textarea
          className="mt-2 min-h-28 w-full rounded-md border border-[var(--border)] px-3 py-2 text-sm leading-6"
          value={event.description}
          onChange={(item) => onChange({ ...event, description: item.target.value })}
        />
      </label>
      <label className="flex items-center gap-2 text-sm font-semibold">
        <input
          type="checkbox"
          checked={event.conflict_flag}
          onChange={(item) => onChange({ ...event, conflict_flag: item.target.checked })}
        />
        Mark as disputed
      </label>
      <button
        className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        disabled={isSaving || !event.id}
        type="submit"
      >
        {isSaving ? "Saving..." : "Save event edit"}
      </button>

      <div className="border-t border-[var(--border)] pt-5">
        <p className="font-semibold">Citations</p>
        <div className="mt-3 space-y-3">
          {event.citations.map((citation) => (
            <article key={citation.id ?? citation.quote} className="rounded-2xl bg-[var(--muted)] p-4">
              <p className="text-sm font-semibold">{citation.document_name}</p>
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                Page {citation.page ?? "n/a"}
              </p>
              <p className="mt-3 text-sm leading-6 text-neutral-700">{citation.quote}</p>
              {citation.viewer_url ? (
                <a
                  className="mt-3 inline-flex rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                  href={citation.viewer_url}
                >
                  Open citation
                </a>
              ) : null}
            </article>
          ))}
        </div>
      </div>
    </form>
  );
}
