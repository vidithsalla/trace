"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AttentionBadges, CandidateBadge, GateBadge, ReviewBadge } from "@/components/v3/states";
import { Badge, Button, Empty, Notice, Panel, PageHeader, Spinner, inputClass } from "@/components/v3/ui";
import { ERROR_TEXT, type Run, apiGet, apiPost, errorMessage, timeAgo } from "@/lib/v3";

const EXAMPLES = [
  "Was invoice 7A approved unconditionally on March 18?",
  "Could invoice 7A be paid once the controller approved it?",
];

export function Investigate({ matterId }: { matterId: string }) {
  const [question, setQuestion] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pendingKey = useRef<string | null>(null);

  const loadRuns = useCallback(async () => {
    const list = await apiGet<Run[]>(`matters/${matterId}/analyses`);
    setRuns(list);
    return list;
  }, [matterId]);

  const loadRun = useCallback(async (id: string) => {
    const run = await apiGet<Run>(`matters/${matterId}/analyses/${id}`);
    setSelected(run);
    return run;
  }, [matterId]);

  useEffect(() => {
    loadRuns().then((list) => (list[0] ? loadRun(list[0].id) : null)).catch((e) => setError(errorMessage(e)));
  }, [loadRuns, loadRun]);

  // Poll while the selected run is still working.
  useEffect(() => {
    if (!selected || !["QUEUED", "RUNNING"].includes(selected.status)) return;
    const timer = setTimeout(() => {
      loadRun(selected.id).then(() => loadRuns()).catch(() => undefined);
    }, 2000);
    return () => clearTimeout(timer);
  }, [selected, loadRun, loadRuns]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (question.trim().length < 3) return;
    setSubmitting(true);
    setError(null);
    pendingKey.current ??= crypto.randomUUID(); // same key if the user double-submits
    try {
      const run = await apiPost<Run>(`matters/${matterId}/analyses`, { question: question.trim() }, pendingKey.current);
      pendingKey.current = null;
      setSelected(run);
      setQuestion("");
      await loadRuns();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Investigate"
        description="Ask a factual question about this matter. Trace retrieves passages from a pinned snapshot of the current sources, searches for opposing evidence, and proposes claims for you to review."
      />
      <form onSubmit={submit} className="mb-6">
        <div className="flex gap-2">
          <input
            className={`${inputClass} h-9`}
            placeholder="e.g. Was invoice 7A approved unconditionally on March 18?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={1000}
            aria-label="Question"
          />
          <Button variant="primary" className="h-9 px-4" disabled={submitting || question.trim().length < 3}>
            {submitting ? <Spinner /> : null} Investigate
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--muted-foreground)]">
          Try:
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="underline-offset-2 hover:underline" onClick={() => setQuestion(example)}>
              {example}
            </button>
          ))}
        </div>
      </form>
      {error ? <div className="mb-4"><Notice tone="bad">{error}</Notice></div> : null}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <Panel title="Recent investigations" padded={false}>
          {runs.length === 0 ? (
            <p className="px-4 py-6 text-sm text-[var(--muted-foreground)]">None yet.</p>
          ) : (
            <ul className="divide-y divide-[var(--border)]">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    onClick={() => loadRun(run.id)}
                    className={`w-full px-4 py-2.5 text-left hover:bg-[var(--subtle)] ${selected?.id === run.id ? "bg-[var(--subtle)]" : ""}`}
                  >
                    <p className="line-clamp-2 text-sm">{run.question}</p>
                    <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                      {run.status.toLowerCase()} · {timeAgo(run.created_at)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <div>{selected ? <RunView matterId={matterId} run={selected} /> : <Empty title="No investigation selected" />}</div>
      </div>
    </>
  );
}

function RunView({ matterId, run }: { matterId: string; run: Run }) {
  const working = run.status === "QUEUED" || run.status === "RUNNING";
  const coverage = run.coverage as { snapshot_spans?: number; primary_candidates?: number; reason?: string; abstention_reason?: string };
  const tokens = run.calls.reduce((sum, c) => sum + (c.prompt_tokens ?? 0) + (c.completion_tokens ?? 0), 0);
  const seconds = run.calls.reduce((sum, c) => sum + c.latency_ms, 0) / 1000;
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{run.question}</h2>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[var(--muted-foreground)]">
          <RunStatus run={run} />
          <span>Model: {run.model?.provider_kind === "mock" ? "deterministic mock" : `${run.model?.model} (${run.model?.provider_kind})`}</span>
          <span>· Retrieval: {run.retrieval_profile}</span>
          {run.calls.length ? <span>· {run.calls.length} model calls, {tokens || "n/a"} tokens, {seconds.toFixed(1)}s</span> : null}
          <span className="font-mono">· snapshot {run.corpus_snapshot_id.slice(0, 8)}</span>
        </div>
      </div>
      {working ? (
        <Notice tone="neutral">
          <span className="inline-flex items-center gap-2"><Spinner /> Retrieving passages, searching for counterevidence and assessing claims. A local model can take a minute.</span>
        </Notice>
      ) : null}
      {run.status === "FAILED" ? (
        <Notice tone="bad">
          This investigation failed: {ERROR_TEXT[run.error_code ?? ""] ?? run.error_code}. No claims were saved.
        </Notice>
      ) : null}
      {run.status === "ABSTAINED" ? (
        <Notice tone="neutral">
          No claims proposed. {coverage.reason === "NO_CANDIDATES" ? "No passage in the current sources matched this question." : coverage.abstention_reason ?? "The model found the passages insufficient."}
        </Notice>
      ) : null}
      {run.claims && run.claims.length > 0 ? (
        <Panel title={`Proposed claims (${run.claims.length})`} padded={false}>
          <ul className="divide-y divide-[var(--border)]">
            {run.claims.map((claim) => (
              <li key={claim.id}>
                <Link href={`/matters/${matterId}/claims/${claim.id}` as never} className="block px-4 py-3 hover:bg-[var(--subtle)]">
                  <p className="text-sm font-medium">{claim.text}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <GateBadge state={claim.source_gate_state} />
                    <CandidateBadge candidate={claim.relation_candidate} />
                    <ReviewBadge state={claim.review_state} stale={claim.basis_state !== "CURRENT"} />
                    <AttentionBadges claim={claim} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
      {!working && run.status === "COMPLETED" ? (
        <p className="text-xs text-[var(--muted-foreground)]">
          Searched {coverage.snapshot_spans ?? "?"} passages in the pinned snapshot; {coverage.primary_candidates ?? "?"} were offered to the model. Retrieval is not exhaustive.
        </p>
      ) : null}
    </div>
  );
}

function RunStatus({ run }: { run: Run }) {
  const tone = { QUEUED: "neutral", RUNNING: "info", COMPLETED: "ok", ABSTAINED: "neutral", FAILED: "bad" } as const;
  return <Badge tone={tone[run.status]}>{run.status.toLowerCase()}</Badge>;
}
