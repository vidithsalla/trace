"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AttentionBadges, CandidateBadge, GateBadge, ReviewBadge } from "@/components/v3/states";
import { Badge, Button, Empty, Mono, Notice, PageHeader, Panel, Spinner } from "@/components/v3/ui";
import { type Alert, type ClaimSummary, apiGet, apiPost, errorMessage, timeAgo } from "@/lib/v3";

// ----------------------------------------------------------------------------------------------
// Review queue
// ----------------------------------------------------------------------------------------------
const FILTERS = [
  ["", "All"],
  ["UNREVIEWED", "Not reviewed"],
  ["ACCEPTED", "Accepted"],
  ["REJECTED", "Rejected"],
  ["UNRESOLVED", "Unresolved"],
  ["attention", "Needs attention"],
] as const;

export function ReviewQueue({ matterId }: { matterId: string }) {
  const [filter, setFilter] = useState<string>("");
  const [claims, setClaims] = useState<ClaimSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = filter === "attention" ? "?needs_attention=true" : filter ? `?review_state=${filter}` : "";
    apiGet<ClaimSummary[]>(`matters/${matterId}/claims${query}`).then(setClaims).catch((e) => setError(errorMessage(e)));
  }, [matterId, filter]);

  return (
    <>
      <PageHeader title="Review" description="Every claim proposed in this matter, with its source check, the model's support suggestion and your decision." />
      <div className="mb-3 flex flex-wrap gap-1">
        {FILTERS.map(([value, label]) => (
          <button key={value} onClick={() => setFilter(value)}
            className={`rounded-md px-2.5 py-1 text-sm ${filter === value ? "bg-[var(--subtle)] font-medium" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"}`}>
            {label}
          </button>
        ))}
      </div>
      {error ? <Notice tone="bad">{error}</Notice> : null}
      {!claims ? <Spinner /> : claims.length === 0 ? (
        <Empty title="No claims here">Run an investigation to propose claims.</Empty>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--border)] bg-[var(--subtle)] text-left text-xs text-[var(--muted-foreground)]">
              <tr>
                <th className="px-4 py-2 font-medium">Claim</th>
                <th className="px-3 py-2 font-medium">Sources</th>
                <th className="px-3 py-2 font-medium">Support (model)</th>
                <th className="px-3 py-2 font-medium">Decision</th>
                <th className="px-3 py-2 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {claims.map((claim) => (
                <tr key={claim.id} className="hover:bg-[var(--subtle)]">
                  <td className="max-w-md px-4 py-2.5">
                    <Link href={`/matters/${matterId}/claims/${claim.id}` as never} className="font-medium hover:underline">{claim.text}</Link>
                    <div className="mt-1 flex gap-1.5"><AttentionBadges claim={claim} />{claim.revision > 1 ? <Badge>rev {claim.revision}</Badge> : null}</div>
                  </td>
                  <td className="px-3 py-2.5"><GateBadge state={claim.source_gate_state} /></td>
                  <td className="px-3 py-2.5"><CandidateBadge candidate={claim.relation_candidate} /></td>
                  <td className="px-3 py-2.5"><ReviewBadge state={claim.review_state} stale={claim.basis_state !== "CURRENT"} /></td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-[var(--muted-foreground)]">{timeAgo(claim.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ----------------------------------------------------------------------------------------------
// Changes requiring review
// ----------------------------------------------------------------------------------------------
type Change = Alert & { claim: ClaimSummary };

const KIND: Record<string, { label: string; tone: "warn" | "info" | "neutral"; explain: (d: Record<string, unknown>) => string }> = {
  STALE_SOURCE: {
    label: "Cited source superseded", tone: "warn",
    explain: (d) => `A document this claim cites moved from revision ${d.superseded_revision} to ${d.new_revision}. Any earlier decision was made against the old text.`,
  },
  POTENTIAL_NEW_EVIDENCE: {
    label: "New document may matter", tone: "info",
    explain: () => "A new or revised document overlaps this claim's subject. This is a candidate signal and can be wrong in either direction.",
  },
  STALE_CLAIM: { label: "Claim edited after decision", tone: "neutral", explain: () => "The wording changed after a decision; the new revision is unreviewed." },
};

export function ChangesList({ matterId }: { matterId: string }) {
  const [rows, setRows] = useState<Change[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => apiGet<Change[]>(`matters/${matterId}/changes`).then(setRows), [matterId]);
  useEffect(() => { load().catch((e) => setError(errorMessage(e))); }, [load]);

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setError(null);
    try { await fn(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(null); }
  }

  return (
    <>
      <PageHeader title="Changes" description="Sources changed after claims were proposed or reviewed. A superseded source always needs a re-check; a possibly relevant new document is a cautious hint you can dismiss." />
      {error ? <div className="mb-3"><Notice tone="bad">{error}</Notice></div> : null}
      {!rows ? <Spinner /> : rows.length === 0 ? <Empty title="Nothing needs re-review">Every claim's evidence matches the current sources.</Empty> : (
        <div className="space-y-2">
          {rows.map((row) => {
            const kind = KIND[row.kind];
            return (
              <Panel key={row.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2"><Badge tone={kind.tone}>{kind.label}</Badge><span className="text-xs text-[var(--muted-foreground)]">{timeAgo(row.created_at)}</span></div>
                    <Link href={`/matters/${matterId}/claims/${row.claim_id}` as never} className="mt-1.5 block font-medium hover:underline">{row.claim.text}</Link>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">{kind.explain(row.detail)}</p>
                    <div className="mt-2 flex gap-1.5"><ReviewBadge state={row.claim.review_state} stale={row.claim.basis_state !== "CURRENT"} /></div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button disabled={busy === row.id} onClick={() => run(row.id, () => apiPost(`matters/${matterId}/claims/${row.claim_id}/revisions`, { expected_claim_revision: row.claim.revision }))}>
                      {busy === row.id ? <Spinner /> : null} Re-check
                    </Button>
                    {row.kind === "POTENTIAL_NEW_EVIDENCE" ? (
                      <Button variant="ghost" disabled={busy === row.id} onClick={() => run(row.id, () => apiPost(`matters/${matterId}/changes/${row.id}/dismiss`))}>Dismiss</Button>
                    ) : null}
                  </div>
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </>
  );
}

// ----------------------------------------------------------------------------------------------
// Sources (documents and immutable versions)
// ----------------------------------------------------------------------------------------------
type Version = { id: string; revision_no: number; state: string; source_sha256: string | null; provenance: string; file_name: string; change_note: string | null; created_at: string; span_count: number; warnings: string[] };
type Source = { id: string; title: string; mime_type: string; ingest_status: string; current_version_id: string | null; versions: Version[] };

export function SourcesList({ matterId }: { matterId: string }) {
  const [rows, setRows] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const load = useCallback(() => apiGet<Source[]>(`matters/${matterId}/sources`).then(setRows), [matterId]);
  useEffect(() => { load().catch((e) => setError(errorMessage(e))); }, [load]);
  useEffect(() => {
    if (!rows?.some((r) => r.versions.some((v) => v.state === "STAGING"))) return;
    const timer = setTimeout(() => load().catch(() => undefined), 2000);
    return () => clearTimeout(timer);
  }, [rows, load]);

  async function upload(file: File, document?: Source) {
    setError(null);
    setNotice(null);
    const form = new FormData();
    form.append("file", file);
    try {
      if (document) {
        form.append("expected_revision", String(document.versions[0]?.revision_no ?? 0));
        await apiPost(`matters/${matterId}/documents/${document.id}/versions`, form);
        setNotice(`Uploaded a new version of ${document.title}. Claims citing the old version will be flagged once it is processed.`);
      } else {
        await apiPost(`matters/${matterId}/documents/upload`, form);
        setNotice(`Uploaded ${file.name}.`);
      }
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      <PageHeader title="Sources" description="Documents in this matter. Every upload is an immutable version; a correction becomes a new revision and the old one stays available for past decisions."
        actions={<FilePick label="Add document" onPick={(f) => upload(f)} />} />
      {notice ? <div className="mb-3"><Notice tone="ok">{notice}</Notice></div> : null}
      {error ? <div className="mb-3"><Notice tone="bad">{error}</Notice></div> : null}
      {!rows ? <Spinner /> : rows.length === 0 ? <Empty title="No documents yet">Add a PDF, DOCX, XLSX, CSV or TXT file.</Empty> : (
        <div className="space-y-2">
          {rows.map((doc) => (
            <Panel key={doc.id} title={<Link className="hover:underline" href={`/matters/${matterId}/documents/${doc.id}` as never}>{doc.title}</Link>}
              actions={<FilePick label="Upload new version" onPick={(f) => upload(f, doc)} />} padded={false}>
              <table className="w-full table-fixed text-sm">
                <colgroup>
                  <col className="w-28" /><col className="w-32" /><col /><col className="w-48" /><col className="w-44" /><col className="w-24" />
                </colgroup>
                <tbody className="divide-y divide-[var(--border)]">
                  {doc.versions.map((v) => (
                    <tr key={v.id}>
                      <td className="px-4 py-2 font-medium">Revision {v.revision_no}</td>
                      <td className="px-3 py-2"><VersionState version={v} current={doc.current_version_id === v.id} /></td>
                      <td className="truncate px-3 py-2 text-[var(--muted-foreground)]">{v.change_note ?? v.file_name}</td>
                      <td className="px-3 py-2 text-xs text-[var(--muted-foreground)]">{v.span_count} passages{v.warnings.length ? ` · ${v.warnings.join(", ").toLowerCase()}` : ""}</td>
                      <td className="px-3 py-2"><Mono>{v.source_sha256 ? `sha256 ${v.source_sha256.slice(0, 12)}` : "hash unknown (legacy)"}</Mono></td>
                      <td className="whitespace-nowrap px-4 py-2 text-right text-xs text-[var(--muted-foreground)]">{timeAgo(v.created_at)}</td>
                    </tr>
                  ))}
                  {doc.versions.length === 0 ? <tr><td className="px-4 py-2 text-[var(--muted-foreground)]">Processing…</td></tr> : null}
                </tbody>
              </table>
            </Panel>
          ))}
        </div>
      )}
    </>
  );
}

function VersionState({ version, current }: { version: Version; current: boolean }) {
  if (current) return <Badge tone="ok">Current</Badge>;
  if (version.state === "STAGING") return <Badge tone="info"><Spinner /> Processing</Badge>;
  if (version.state === "RETIRED") return <Badge>Superseded</Badge>;
  if (version.state === "FAILED") return <Badge tone="bad">Failed</Badge>;
  return <Badge>{version.state.toLowerCase()}</Badge>;
}

function FilePick({ label, onPick }: { label: string; onPick: (f: File) => void }) {
  return (
    <label className="inline-flex h-8 cursor-pointer items-center rounded-md border border-[var(--border-strong)] bg-[var(--surface)] px-3 text-sm font-medium hover:bg-[var(--subtle)]">
      {label}
      <input type="file" className="sr-only" accept=".pdf,.docx,.xlsx,.csv,.txt"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = ""; }} />
    </label>
  );
}

// ----------------------------------------------------------------------------------------------
// Evidence packets
// ----------------------------------------------------------------------------------------------
type Packet = { id: string; inclusion_policy: string; claim_count: number; manifest_sha256: string; files: Record<string, { sha256: string; bytes: number }>; created_at: string | null };

export function Packets({ matterId }: { matterId: string }) {
  const [packets, setPackets] = useState<Packet[] | null>(null);
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [includeAll, setIncludeAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [p, c] = await Promise.all([apiGet<Packet[]>(`matters/${matterId}/packets`), apiGet<ClaimSummary[]>(`matters/${matterId}/claims`)]);
    setPackets(p);
    setClaims(c);
  }, [matterId]);
  useEffect(() => { load().catch((e) => setError(errorMessage(e))); }, [load]);

  const exportable = (c: ClaimSummary) => c.review_state === "ACCEPTED" && c.basis_state === "CURRENT" && c.coverage_state === "CURRENT" && c.source_gate_state === "VERIFIED";
  const visible = includeAll ? claims : claims.filter(exportable);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await apiPost(`matters/${matterId}/packets`, { claim_ids: [...selected], inclusion_policy: includeAll ? "include_all_labeled" : "accepted_current_only" });
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Evidence packets" description="Export reviewed findings with the exact source versions, passages, decisions and checksums behind them. A packet never changes after it is created." />
      {error ? <div className="mb-3"><Notice tone="bad">{error}</Notice></div> : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="New packet" actions={
          <label className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
            <input type="checkbox" checked={includeAll} onChange={(e) => { setIncludeAll(e.target.checked); setSelected(new Set()); }} />
            Include unreviewed and stale claims (labeled)
          </label>}>
          {visible.length === 0 ? <p className="text-sm text-[var(--muted-foreground)]">No claims are accepted against current sources yet.</p> : (
            <ul className="space-y-1.5">
              {visible.map((c) => (
                <li key={c.id}>
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-1" checked={selected.has(c.id)}
                      onChange={(e) => { const next = new Set(selected); if (e.target.checked) next.add(c.id); else next.delete(c.id); setSelected(next); }} />
                    <span>{c.text}{!exportable(c) ? <span className="ml-1.5"><ReviewBadge state={c.review_state} stale={c.basis_state !== "CURRENT"} /></span> : null}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <Button variant="primary" className="mt-4" disabled={busy || selected.size === 0} onClick={create}>
            {busy ? <Spinner /> : null} Create packet ({selected.size})
          </Button>
        </Panel>
        <Panel title="Created packets" padded={false}>
          {!packets ? <div className="p-4"><Spinner /></div> : packets.length === 0 ? <p className="px-4 py-6 text-sm text-[var(--muted-foreground)]">None yet.</p> : (
            <ul className="divide-y divide-[var(--border)]">
              {packets.map((p) => (
                <li key={p.id} className="px-4 py-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{p.claim_count} finding{p.claim_count === 1 ? "" : "s"}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{p.created_at ? timeAgo(p.created_at) : ""}</span>
                  </div>
                  <p className="mt-0.5"><Mono>manifest sha256 {p.manifest_sha256.slice(0, 16)}</Mono></p>
                  <div className="mt-1.5 flex flex-wrap gap-3 text-xs">
                    {Object.keys(p.files).map((name) => (
                      <a key={name} className="underline underline-offset-2" href={`/api/v3/matters/${matterId}/packets/${p.id}/files/${name}`}>{name}</a>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
