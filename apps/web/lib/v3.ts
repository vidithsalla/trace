// Client for the V3 evidence-review API (through the same-origin /api/v3 proxy).

export type ReviewState = "UNREVIEWED" | "ACCEPTED" | "REJECTED" | "UNRESOLVED";
export type GateState = "VERIFIED" | "INVALID" | "UNAVAILABLE";
export type Candidate =
  | "SUPPORT_CANDIDATE"
  | "CONTRADICTION_CANDIDATE"
  | "MIXED"
  | "NOT_ESTABLISHED"
  | "UNCERTAIN"
  | "UNASSESSED";

export type ClaimSummary = {
  id: string;
  run_id: string;
  text: string;
  revision: number;
  review_seq: number;
  review_state: ReviewState;
  basis_state: "CURRENT" | "STALE_SOURCE";
  coverage_state: "CURRENT" | "POTENTIAL_NEW_EVIDENCE";
  source_gate_state: GateState;
  source_gate_reasons: string[];
  relation_candidate: Candidate;
  evidence_sha256: string;
  updated_at: string;
};

export type SourceView = {
  source_span_id: string;
  text: string;
  context_before: string;
  context_after: string;
  page: number;
  start: number;
  end: number;
  quote_sha256: string;
  document_id: string;
  document_title: string | null;
  document_version_id: string;
  revision_no: number;
  version_state: string;
  is_current_version: boolean;
  provenance: string;
};

export type EvidenceView = {
  evidence_ref: string;
  role: "supporting" | "qualifying" | "opposing" | "other";
  cited_by_model: boolean;
  relation_candidate: string;
  reason_code: string | null;
  quote_integrity: GateState;
  integrity_reason: string | null;
  retrieval_role: "primary" | "counterevidence";
  source: SourceView;
};

export type Alert = {
  id: string;
  claim_id: string;
  claim_revision: number;
  kind: "STALE_SOURCE" | "STALE_CLAIM" | "POTENTIAL_NEW_EVIDENCE";
  status: string;
  detail: Record<string, unknown>;
  detector_version: string;
  created_at: string;
};

export type ClaimDetail = ClaimSummary & {
  viewing_revision: number;
  viewing_text: string;
  viewing_source_gate_state: GateState;
  viewing_relation_candidate: Candidate;
  coverage: Record<string, unknown>;
  open_questions: string[];
  question: string | null;
  model: Record<string, unknown> | null;
  evidence: EvidenceView[];
  revisions: {
    revision: number;
    text: string;
    actor_type: string;
    change_reason: string | null;
    source_gate_state: GateState;
    relation_candidate: Candidate;
    created_at: string;
  }[];
  events: {
    id: string;
    seq: number;
    action: string;
    revision: number;
    reason_code: string | null;
    note: string | null;
    actor: string | null;
    created_at: string;
  }[];
  alerts: Alert[];
};

export type Run = {
  id: string;
  question: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "ABSTAINED" | "FAILED";
  error_code: string | null;
  retrieval_profile: string;
  model: { provider_kind?: string; model?: string; endpoint_class?: string } & Record<string, unknown>;
  corpus_snapshot_id: string;
  coverage: Record<string, unknown>;
  calls: { purpose: string; status: string; latency_ms: number; prompt_tokens?: number | null; completion_tokens?: number | null }[];
  created_at: string;
  completed_at: string | null;
  claims?: ClaimSummary[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public body: unknown,
  ) {
    super(code);
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    window.location.assign("/sign-in");
    throw new ApiError(401, "UNAUTHENTICATED", null);
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body?.detail;
    const code = typeof detail === "object" && detail?.code ? detail.code : typeof detail === "string" ? detail : `HTTP_${response.status}`;
    throw new ApiError(response.status, code, body);
  }
  return body as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return fetch(`/api/v3/${path}`, { cache: "no-store" }).then((r) => handle<T>(r));
}

export function apiPost<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const headers: Record<string, string> = { "X-Trace-Request": "1" };
  if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  headers["Idempotency-Key"] = idempotencyKey ?? crypto.randomUUID();
  return fetch(`/api/v3/${path}`, {
    method: "POST",
    headers,
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => handle<T>(r));
}

export const ERROR_TEXT: Record<string, string> = {
  CLAIM_OR_EVIDENCE_CHANGED: "This claim or its evidence changed since you opened it. Review the latest version.",
  REVIEW_STATE_CHANGED: "Someone else recorded a decision on this claim while you were reviewing. Reload to see it.",
  SOURCE_NOT_VERIFIED: "A cited passage failed source verification, so this claim cannot be accepted.",
  STALE_BASIS: "A cited document has a newer version. Re-check the claim against current sources first.",
  COVERAGE_OUTDATED: "A new document may affect this claim. Re-check it or dismiss the alert first.",
  REVIEW_NOT_AUTHORIZED: "Your role on this matter cannot record review decisions.",
  IDEMPOTENCY_KEY_REUSED: "This request was already submitted with different content.",
  provider_unavailable: "The model server is not reachable. Is Ollama running?",
  provider_config_error: "The model provider is not configured correctly.",
  provider_timeout: "The model took too long to respond.",
  schema_error: "The model returned output that did not match the required format.",
  worker_lost: "The background worker stopped before finishing. Run the investigation again.",
  embedding_unavailable: "The embedding model is not reachable. Is Ollama running?",
  call_budget_exceeded: "The run hit its limit on model calls.",
  NOTHING_TO_EXPORT: "None of the selected claims are accepted against current sources.",
  DOCUMENT_REVISION_CHANGED: "Someone uploaded a newer version first. Reload and try again.",
  IDENTICAL_CONTENT: "That file is identical to the current version.",
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return ERROR_TEXT[error.code] ?? `Request failed (${error.code}).`;
  return "Something went wrong. Please try again.";
}

export function timeAgo(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}
