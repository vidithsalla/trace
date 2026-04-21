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

type GroundedQAResponse = {
  answer: string;
  short_answer: string;
  confidence: string;
  citations: Citation[];
  open_questions: string[];
  unsupported_claims_detected: boolean;
  ai_run_id: string | null;
};

const EXAMPLE_QUESTION =
  "What evidence suggests Northshore knew of the defect before shipment?";

export function AskPanel({ matterId }: { matterId: string }) {
  const [question, setQuestion] = useState(EXAMPLE_QUESTION);
  const [response, setResponse] = useState<GroundedQAResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [evidenceOnly, setEvidenceOnly] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) {
      return;
    }

    setError(null);
    setIsAsking(true);
    const askResponse = await fetch(`/api/matters/${matterId}/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, evidence_only: evidenceOnly, limit: 6 }),
    });
    setIsAsking(false);

    if (askResponse.status === 401) {
      window.location.assign("/sign-in");
      return;
    }
    if (!askResponse.ok) {
      setError("Trace could not complete this grounded answer.");
      return;
    }
    setResponse(await askResponse.json());
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
      <section className="space-y-5">
        <form
          onSubmit={handleSubmit}
          className="rounded-3xl border border-[var(--border)] bg-white p-5"
        >
          <label className="text-sm font-semibold" htmlFor="grounded-question">
            Matter-scoped question
          </label>
          <textarea
            id="grounded-question"
            className="mt-3 min-h-32 w-full rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm leading-6 outline-none focus:border-[var(--accent)]"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={evidenceOnly}
                onChange={(event) => setEvidenceOnly(event.target.checked)}
              />
              Evidence-only mode
            </label>
            <button
              className="rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
              disabled={isAsking || !question.trim()}
              type="submit"
            >
              {isAsking ? "Asking..." : "Ask Trace"}
            </button>
          </div>
          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
        </form>

        {response ? (
          <article className="rounded-3xl border border-[var(--border)] bg-[var(--muted)] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">
                  Grounded answer
                </p>
                <h3 className="mt-2 text-xl font-semibold">{response.short_answer}</h3>
              </div>
              <span className={confidenceClass(response.confidence)}>
                {response.confidence} confidence
              </span>
            </div>
            {!evidenceOnly ? (
              <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-neutral-800">
                {response.answer}
              </p>
            ) : (
              <p className="mt-5 text-sm leading-7 text-neutral-700">
                Evidence-only mode is on. Review the validated citations in the evidence panel.
              </p>
            )}
            {response.open_questions.length > 0 ? (
              <div className="mt-5 rounded-2xl border border-[var(--border)] bg-white p-4">
                <p className="text-sm font-semibold">Open questions</p>
                <ul className="mt-2 space-y-2 text-sm text-neutral-700">
                  {response.open_questions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {response.ai_run_id ? (
              <p className="mt-4 text-xs text-neutral-500">
                AI run:{" "}
                <a className="font-semibold text-[var(--accent)]" href={`/api/ai-runs/${response.ai_run_id}`}>
                  {response.ai_run_id}
                </a>
              </p>
            ) : null}
          </article>
        ) : (
          <div className="rounded-3xl border border-dashed border-[var(--border)] p-5 text-sm leading-7 text-neutral-600">
            Ask a question after documents have been ingested. Trace will answer only with
            validated matter evidence.
          </div>
        )}
      </section>

      <section className="rounded-3xl border border-[var(--border)] bg-white p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--warm)]">Evidence</p>
            <h3 className="mt-2 text-xl font-semibold">Validated citations</h3>
          </div>
          <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
            {response?.citations.length ?? 0}
          </span>
        </div>
        <div className="mt-5 space-y-3">
          {response?.citations.map((citation, index) => (
            <article
              key={citation.id ?? `${citation.document_id}-${index}`}
              className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold">{citation.document_name}</p>
                <span className="text-xs uppercase tracking-[0.16em] text-[var(--warm)]">
                  Page {citation.page ?? "n/a"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-neutral-700">{citation.quote}</p>
              {citation.viewer_url ? (
                <a
                  className="mt-4 inline-flex rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
                  href={citation.viewer_url}
                >
                  Open citation
                </a>
              ) : null}
            </article>
          ))}
          {response && response.citations.length === 0 ? (
            <p className="rounded-2xl border border-[var(--border)] p-4 text-sm text-neutral-600">
              No validated citations were available for this answer.
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function confidenceClass(confidence: string) {
  const base = "rounded-full px-3 py-1 text-xs font-semibold text-white";
  if (confidence === "high") {
    return `${base} bg-emerald-700`;
  }
  if (confidence === "medium") {
    return `${base} bg-[var(--accent)]`;
  }
  return `${base} bg-amber-700`;
}
