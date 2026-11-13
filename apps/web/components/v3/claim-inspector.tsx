"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AttentionBadges, CandidateBadge, GateBadge, REASON_LABEL, ROLE_LABEL, ReviewBadge } from "@/components/v3/states";
import { Badge, Button, Mono, Notice, Panel, Spinner, inputClass } from "@/components/v3/ui";
import { ApiError, type ClaimDetail, type EvidenceView, apiGet, apiPost, errorMessage, timeAgo } from "@/lib/v3";

const REASONS = [
  ["SOURCE_REVIEWED", "Checked against the sources"],
  ["CONDITION_OMITTED", "Leaves out a condition"],
  ["CONTRADICTED_BY_LATER_SOURCE", "Contradicted by a later source"],
  ["WRONG_ENTITY", "About a different entity"],
  ["INSUFFICIENT_EVIDENCE", "Not enough evidence"],
  ["NEEDS_MORE_DOCUMENTS", "Needs more documents"],
  ["OTHER", "Other"],
] as const;

export function ClaimInspector({ matterId, claimId, revision }: { matterId: string; claimId: string; revision?: number }) {
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await apiGet<ClaimDetail>(`matters/${matterId}/claims/${claimId}${revision ? `?revision=${revision}` : ""}`);
    setClaim(data);
    return data;
  }, [matterId, claimId, revision]);

  useEffect(() => {
    load().catch((e) => setError(errorMessage(e)));
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    setConflict(false);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorMessage(e));
      if (e instanceof ApiError && e.status === 409) setConflict(true);
    } finally {
      setBusy(false);
    }
  }

  if (!claim) return error ? <Notice tone="bad">{error}</Notice> : <Spinner />;
  const viewingOld = claim.viewing_revision !== claim.revision;
  const groups = (["supporting", "qualifying", "opposing", "other"] as const)
    .map((role) => [role, claim.evidence.filter((e) => e.role === role)] as const)
    .filter(([, items]) => items.length > 0);
  const openAlerts = claim.alerts.filter((a) => a.status === "OPEN");
  const lastDecision = [...claim.events].reverse().find((e) => ["ACCEPT", "REJECT", "UNRESOLVED"].includes(e.action));
  const coverage = claim.coverage as { assessed_spans?: number; counterevidence_candidates?: number; snapshot_spans?: number };
  const counter = claim.evidence.filter((e) => e.retrieval_role === "counterevidence").length;

  return (
    <div>
      <nav className="mb-3 text-xs text-[var(--muted-foreground)]">
        <Link href={`/matters/${matterId}/review` as never} className="hover:text-[var(--foreground)]">Review</Link>
        <span className="mx-1.5">/</span>Claim
      </nav>
      {claim.question ? <p className="mb-1 text-sm text-[var(--muted-foreground)]">Question: {claim.question}</p> : null}
      <h1 className="text-lg font-semibold leading-snug tracking-tight">{claim.viewing_text}</h1>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <span>Revision {claim.viewing_revision} of {claim.revision}</span>
        <AttentionBadges claim={claim} />
      </div>

      {viewingOld ? (
        <div className="mt-4">
          <Notice tone="neutral">
            You are viewing revision {claim.viewing_revision}, a historical record.{" "}
            <Link className="underline" href={`/matters/${matterId}/claims/${claimId}` as never}>Open the current revision</Link>.
          </Notice>
        </div>
      ) : null}

      {/* The three trust layers, always side by side and never merged. */}
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <Layer label="1 · Source integrity" badge={<GateBadge state={claim.viewing_source_gate_state} />}>
          {claim.viewing_source_gate_state === "VERIFIED"
            ? "Every cited passage exists unchanged in the stated document version."
            : `Problem: ${claim.source_gate_reasons.join(", ") || "unknown"}.`}
        </Layer>
        <Layer label="2 · Support (model suggestion)" badge={<CandidateBadge candidate={claim.viewing_relation_candidate} />}>
          Suggested by {String(claim.model?.model ?? "model")} ({String(claim.model?.provider_kind ?? "?")}). A suggestion, not a verification.
        </Layer>
        <Layer label="3 · Your decision" badge={<ReviewBadge state={claim.review_state} stale={claim.basis_state !== "CURRENT"} />}>
          {lastDecision ? `${lastDecision.actor ?? "Reviewer"}, ${timeAgo(lastDecision.created_at)}, on revision ${lastDecision.revision}.` : "No decision recorded for this revision."}
        </Layer>
      </div>

      {!viewingOld && openAlerts.length > 0 ? (
        <div className="mt-4 space-y-2">
          {openAlerts.map((alert) => (
            <AlertBanner key={alert.id} kind={alert.kind} detail={alert.detail} busy={busy}
              onRecheck={() => act(() => apiPost(`matters/${matterId}/claims/${claimId}/revisions`, { expected_claim_revision: claim.revision }))}
              onDismiss={alert.kind === "POTENTIAL_NEW_EVIDENCE" ? () => act(() => apiPost(`matters/${matterId}/changes/${alert.id}/dismiss`)) : undefined}
            />
          ))}
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <Notice tone="bad">
            {error}{" "}
            {conflict ? <button className="underline" onClick={() => load()}>Reload</button> : null}
          </Notice>
        </div>
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-5">
          {groups.map(([role, items]) => (
            <section key={role}>
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                {ROLE_LABEL[role]} <span className="font-normal text-[var(--muted-foreground)]">{items.length}</span>
              </h2>
              <div className="space-y-2">
                {items.map((item) => <Passage key={item.source.source_span_id} matterId={matterId} item={item} />)}
              </div>
            </section>
          ))}
          <p className="text-xs text-[var(--muted-foreground)]">
            {coverage.assessed_spans ?? claim.evidence.length} passages assessed, {counter} of them from a search for opposing evidence
            {coverage.snapshot_spans ? `, out of ${coverage.snapshot_spans} in the snapshot` : ""}. This search is not exhaustive: no opposing
            passage here does not mean none exists.
          </p>
        </div>
        <aside className="space-y-4">
          {!viewingOld ? <DecisionPanel claim={claim} busy={busy} onSubmit={(payload, key) => act(() => apiPost(`matters/${matterId}/claims/${claimId}/reviews`, payload, key))} /> : null}
          {!viewingOld ? (
            <EditPanel claim={claim} busy={busy}
              onEdit={(text) => act(() => apiPost(`matters/${matterId}/claims/${claimId}/revisions`, { expected_claim_revision: claim.revision, text }))}
              onRecheck={() => act(() => apiPost(`matters/${matterId}/claims/${claimId}/revisions`, { expected_claim_revision: claim.revision }))}
            />
          ) : null}
          <History claim={claim} matterId={matterId} claimId={claimId} />
        </aside>
      </div>
    </div>
  );
}

function Layer({ label, badge, children }: { label: string; badge: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <p className="text-xs font-medium text-[var(--muted-foreground)]">{label}</p>
      <div className="mt-1.5">{badge}</div>
      <p className="mt-2 text-xs text-[var(--muted-foreground)]">{children}</p>
    </div>
  );
}

function AlertBanner({ kind, detail, busy, onRecheck, onDismiss }: {
  kind: string; detail: Record<string, unknown>; busy: boolean; onRecheck: () => void; onDismiss?: () => void;
}) {
  const text = kind === "STALE_SOURCE"
    ? `A cited document now has revision ${detail.new_revision}; this claim's evidence comes from revision ${detail.superseded_revision}. The earlier decision is kept in history but no longer counts as current.`
    : kind === "POTENTIAL_NEW_EVIDENCE"
      ? "A newly added document mentions the same subject and may change this finding. Trace has not decided either way."
      : "The claim text changed after a decision. The new revision needs its own review.";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--warn-border)] bg-[var(--warn-bg)] px-3 py-2 text-sm text-[var(--warn)]">
      <span>{text}</span>
      <span className="flex gap-2">
        {kind !== "STALE_CLAIM" ? <Button disabled={busy} onClick={onRecheck}>Re-check against current sources</Button> : null}
        {onDismiss ? <Button variant="ghost" disabled={busy} onClick={onDismiss}>Dismiss</Button> : null}
      </span>
    </div>
  );
}

function highlight(text: string) {
  return <mark>{text}</mark>;
}

function Passage({ matterId, item }: { matterId: string; item: EvidenceView }) {
  const s = item.source;
  // Trim context to ~160 chars on word boundaries so snippets never start or end mid-word.
  const before = s.context_before.length > 160
    ? `…${s.context_before.slice(-160).replace(/^\S*\s/, "")}`
    : s.context_before;
  const after = s.context_after.length > 160
    ? `${s.context_after.slice(0, 160).replace(/\s\S*$/, "")}…`
    : s.context_after;
  return (
    <article className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
      <header className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-3 py-2 text-xs">
        <Link href={`/matters/${matterId}/documents/${s.document_id}` as never} className="font-medium hover:underline">
          {s.document_title ?? "Document"}
        </Link>
        <span className="text-[var(--muted-foreground)]">revision {s.revision_no} · page {s.page}</span>
        {!s.is_current_version ? <Badge tone="warn">Superseded version</Badge> : null}
        {item.cited_by_model ? <Badge>Cited by model</Badge> : null}
        {item.retrieval_role === "counterevidence" ? <Badge tone="info">Found by counterevidence search</Badge> : null}
        {item.reason_code ? <span className="text-[var(--muted-foreground)]">{REASON_LABEL[item.reason_code] ?? item.reason_code}</span> : null}
        {item.quote_integrity !== "VERIFIED" ? <Badge tone="bad">{item.integrity_reason ?? item.quote_integrity}</Badge> : null}
      </header>
      <p className="quote px-3 py-2.5 text-sm leading-relaxed">
        <span className="text-[var(--muted-foreground)]">{before}</span>
        {highlight(s.text)}
        <span className="text-[var(--muted-foreground)]">{after}</span>
      </p>
      <footer className="border-t border-[var(--border)] px-3 py-1.5">
        <Mono>chars {s.start}–{s.end} · sha256 {s.quote_sha256.slice(0, 12)} · {item.evidence_ref}</Mono>
      </footer>
    </article>
  );
}

type ReviewPayload = {
  decision: string;
  expected_claim_revision: number;
  expected_evidence_sha256: string;
  expected_review_seq: number;
  reason_code: string;
  note: string | null;
};

function DecisionPanel({ claim, busy, onSubmit }: { claim: ClaimDetail; busy: boolean; onSubmit: (p: ReviewPayload, key: string) => void }) {
  const [decision, setDecision] = useState<"accept" | "reject" | "unresolved">("accept");
  const [reason, setReason] = useState("SOURCE_REVIEWED");
  const [note, setNote] = useState("");
  const key = useRef(crypto.randomUUID());
  useEffect(() => {
    key.current = crypto.randomUUID(); // new logical action whenever the claim state changes
  }, [claim.review_seq, claim.revision]);

  const blocker =
    claim.source_gate_state !== "VERIFIED" ? "A cited passage failed source verification."
      : claim.basis_state !== "CURRENT" ? "A cited source was superseded. Re-check first."
        : claim.coverage_state !== "CURRENT" ? "A new document may matter. Re-check or dismiss first."
          : null;
  const options = [
    ["accept", "Accept for packet"],
    ["reject", "Reject"],
    ["unresolved", "Unresolved"],
  ] as const;
  return (
    <Panel title="Record a decision">
      <div className="grid grid-cols-3 gap-1 rounded-md bg-[var(--subtle)] p-1" role="radiogroup" aria-label="Decision">
        {options.map(([value, label]) => (
          <button key={value} type="button" role="radio" aria-checked={decision === value}
            onClick={() => setDecision(value)}
            className={`rounded px-1 py-1 text-xs font-medium ${decision === value ? "bg-[var(--surface)] shadow-sm" : "text-[var(--muted-foreground)]"}`}>
            {label}
          </button>
        ))}
      </div>
      <label className="mt-3 block text-xs font-medium" htmlFor="reason">Reason</label>
      <select id="reason" className={`${inputClass} mt-1`} value={reason} onChange={(e) => setReason(e.target.value)}>
        {REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <label className="mt-3 block text-xs font-medium" htmlFor="note">Note <span className="font-normal text-[var(--muted-foreground)]">(optional)</span></label>
      <textarea id="note" className={`${inputClass} mt-1 min-h-16`} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      {decision === "accept" && blocker ? <p className="mt-2 text-xs text-[var(--warn)]">{blocker}</p> : null}
      <Button variant="primary" className="mt-3 w-full" disabled={busy || (decision === "accept" && !!blocker)}
        onClick={() => onSubmit({
          decision, expected_claim_revision: claim.revision, expected_evidence_sha256: claim.evidence_sha256,
          expected_review_seq: claim.review_seq, reason_code: reason, note: note.trim() || null,
        }, key.current)}>
        {busy ? <Spinner /> : null} Record decision
      </Button>
      <p className="mt-2 text-xs text-[var(--muted-foreground)]">
        Applies to revision {claim.revision} and this exact evidence set (<Mono>{claim.evidence_sha256.slice(0, 10)}</Mono>). Accepting is not a legal conclusion.
      </p>
    </Panel>
  );
}

function EditPanel({ claim, busy, onEdit, onRecheck }: { claim: ClaimDetail; busy: boolean; onEdit: (t: string) => void; onRecheck: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(claim.text);
  useEffect(() => setText(claim.text), [claim.text]);
  return (
    <Panel title="Revise">
      {editing ? (
        <>
          <textarea className={`${inputClass} min-h-20`} value={text} maxLength={600} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <Button variant="primary" disabled={busy || text.trim() === claim.text} onClick={() => { onEdit(text.trim()); setEditing(false); }}>Save as new revision</Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
          <p className="mt-2 text-xs text-[var(--muted-foreground)]">Editing creates revision {claim.revision + 1} and clears the current decision. The evidence is re-assessed against the new wording.</p>
        </>
      ) : (
        <div className="flex flex-col gap-2">
          <Button onClick={() => setEditing(true)} disabled={busy}>Edit claim text</Button>
          <Button onClick={onRecheck} disabled={busy}>Re-check against current sources</Button>
        </div>
      )}
    </Panel>
  );
}

function History({ claim, matterId, claimId }: { claim: ClaimDetail; matterId: string; claimId: string }) {
  const label: Record<string, string> = { ACCEPT: "Accepted", REJECT: "Rejected", UNRESOLVED: "Marked unresolved", EDIT: "Edited", RECHECK: "Re-checked" };
  return (
    <Panel title="History" padded={false}>
      <ol className="divide-y divide-[var(--border)] text-xs">
        {[...claim.events].reverse().map((event) => (
          <li key={event.id} className="px-4 py-2">
            <p><span className="font-medium">{label[event.action] ?? event.action}</span> · revision {event.revision}</p>
            <p className="text-[var(--muted-foreground)]">{event.actor ?? "?"} · {timeAgo(event.created_at)}{event.reason_code ? ` · ${event.reason_code.toLowerCase().replaceAll("_", " ")}` : ""}</p>
            {event.note ? <p className="mt-0.5 text-[var(--foreground)]">“{event.note}”</p> : null}
          </li>
        ))}
        {claim.revisions.map((rev) => (
          <li key={`r${rev.revision}`} className="px-4 py-2">
            <Link className="hover:underline" href={`/matters/${matterId}/claims/${claimId}?revision=${rev.revision}` as never}>
              <span className="font-medium">Revision {rev.revision}</span>
            </Link>
            <span className="text-[var(--muted-foreground)]"> · {rev.actor_type === "model" ? "proposed by model" : rev.change_reason}</span>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
