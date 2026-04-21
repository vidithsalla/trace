"use client";

import { FormEvent, useState } from "react";

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

type Contradiction = {
  claim_a: string;
  claim_b: string;
  why_conflict: string;
  severity: string;
  citations_a: Citation[];
  citations_b: Citation[];
  side_a_label: string | null;
  side_b_label: string | null;
  confidence: string;
};

type ContradictionResponse = {
  topic: string;
  contradictions: Contradiction[];
  ambiguities: string[];
  evidence_count: number;
  ai_run_id: string | null;
};

const TOPIC_OPTIONS = [
  "notice timing",
  "payment approval authority",
  "defect knowledge",
];

export function ContradictionsPanel({ matterId }: { matterId: string }) {
  const [topic, setTopic] = useState(TOPIC_OPTIONS[0]);
  const [response, setResponse] = useState<ContradictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  async function runContradictionFinder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!topic.trim()) {
      return;
    }
    setError(null);
    setIsRunning(true);
    const finderResponse = await fetch(`/api/matters/${matterId}/contradictions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic, limit: 16 }),
    });
    setIsRunning(false);
    if (finderResponse.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!finderResponse.ok) {
      setError("Trace could not complete contradiction analysis for this topic.");
      return;
    }
    setResponse(await finderResponse.json());
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={runContradictionFinder}
        className="rounded-3xl border border-[var(--border)] bg-white p-5"
      >
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
              Conservative inconsistency scan
            </p>
            <h3 className="mt-2 text-xl font-semibold">Find contradiction candidates</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-700">
              Trace only labels a contradiction when both sides have validated citations. If one
              side is thin, the result stays in ambiguity instead of overstating the record.
            </p>
          </div>
          <button
            className="rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
            disabled={isRunning || !topic.trim()}
            type="submit"
          >
            {isRunning ? "Analyzing..." : "Run finder"}
          </button>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input
            className="min-h-12 flex-1 rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 text-sm outline-none focus:border-[var(--accent)]"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Try: payment approval authority"
          />
          <div className="flex flex-wrap gap-2">
            {TOPIC_OPTIONS.map((item) => (
              <button
                key={item}
                className="rounded-full border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--accent)]"
                type="button"
                onClick={() => setTopic(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      </form>

      {response ? (
        <section className="space-y-5">
          <div className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
                  Topic
                </p>
                <h3 className="mt-2 text-2xl font-semibold">{response.topic}</h3>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold">
                <span className="rounded-full bg-white px-3 py-2 text-[var(--accent)]">
                  {response.evidence_count} evidence item{response.evidence_count === 1 ? "" : "s"}
                </span>
                <span className="rounded-full bg-white px-3 py-2 text-[var(--accent)]">
                  {response.contradictions.length} contradiction{response.contradictions.length === 1 ? "" : "s"}
                </span>
              </div>
            </div>
            {response.ai_run_id ? (
              <p className="mt-3 text-xs text-neutral-500">AI run: {response.ai_run_id}</p>
            ) : null}
          </div>

          {response.contradictions.map((item, index) => (
            <article
              key={`${item.claim_a}-${index}`}
              className="rounded-3xl border border-[var(--border)] bg-white p-5"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
                  Contradiction candidate
                </p>
                <span className={severityClass(item.severity)}>{item.severity} severity</span>
              </div>
              <p className="mt-4 text-sm leading-7 text-neutral-700">{item.why_conflict}</p>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <EvidenceSide
                  label={item.side_a_label ?? "Side A"}
                  claim={item.claim_a}
                  citations={item.citations_a}
                />
                <EvidenceSide
                  label={item.side_b_label ?? "Side B"}
                  claim={item.claim_b}
                  citations={item.citations_b}
                />
              </div>
            </article>
          ))}

          {response.ambiguities.length > 0 ? (
            <article className="rounded-3xl border border-[var(--border)] bg-white p-5">
              <p className="font-semibold">Ambiguities and limits</p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-neutral-700">
                {response.ambiguities.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ) : null}
        </section>
      ) : (
        <div className="rounded-3xl border border-dashed border-[var(--border)] p-6 text-sm leading-7 text-neutral-600">
          Run the finder on a focused topic. Seed regression topics are notice timing, payment
          approval authority, and defect knowledge.
        </div>
      )}
    </div>
  );
}

function EvidenceSide({
  label,
  claim,
  citations,
}: {
  label: string;
  claim: string;
  citations: Citation[];
}) {
  return (
    <div className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5">
      <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">{label}</p>
      <h4 className="mt-2 text-lg font-semibold">{claim}</h4>
      <div className="mt-4 space-y-3">
        {citations.map((citation, index) => (
          <article
            key={citation.id ?? `${citation.document_id}-${index}`}
            className="rounded-2xl bg-white p-4"
          >
            <p className="font-semibold">{citation.document_name}</p>
            <p className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
              Page {citation.page ?? "n/a"} · {citation.validation_status ?? "candidate"}
            </p>
            <p className="mt-3 text-sm leading-6 text-neutral-700">{citation.quote}</p>
            {citation.viewer_url ? (
              <a
                className="mt-3 inline-flex rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                href={citation.viewer_url}
              >
                Open citation
              </a>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}

function severityClass(severity: string) {
  const base = "rounded-full px-3 py-1 text-xs font-semibold text-white";
  if (severity === "high") {
    return `${base} bg-red-700`;
  }
  if (severity === "medium") {
    return `${base} bg-amber-700`;
  }
  return `${base} bg-neutral-700`;
}
