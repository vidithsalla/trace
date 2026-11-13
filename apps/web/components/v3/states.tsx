// One place that maps backend states to words and colors, so the three trust layers are always
// labeled the same way: source integrity, support candidate (model), human decision.
import { Badge } from "@/components/v3/ui";
import type { Candidate, ClaimSummary, GateState, ReviewState } from "@/lib/v3";

export function GateBadge({ state }: { state: GateState }) {
  const map = {
    VERIFIED: ["ok", "Source verified"],
    INVALID: ["bad", "Source invalid"],
    UNAVAILABLE: ["warn", "Source unavailable"],
  } as const;
  const [tone, label] = map[state];
  return (
    <Badge tone={tone} title="Deterministic check: the quoted passage exists unchanged in this document version and matter.">
      {label}
    </Badge>
  );
}

const CANDIDATE: Record<Candidate, ["ok" | "warn" | "bad" | "neutral", string]> = {
  SUPPORT_CANDIDATE: ["ok", "Appears supported"],
  CONTRADICTION_CANDIDATE: ["bad", "Appears contradicted"],
  MIXED: ["warn", "Conflicting evidence"],
  NOT_ESTABLISHED: ["neutral", "Not established"],
  UNCERTAIN: ["neutral", "Uncertain"],
  UNASSESSED: ["neutral", "Not assessed"],
};

export function CandidateBadge({ candidate }: { candidate: Candidate }) {
  const [tone, label] = CANDIDATE[candidate];
  return (
    <Badge tone={tone} title="Model suggestion only. It is not a verification and not a decision.">
      {label}
      <span className="font-normal opacity-70">· model</span>
    </Badge>
  );
}

export function ReviewBadge({ state, stale }: { state: ReviewState; stale?: boolean }) {
  const map = {
    UNREVIEWED: ["neutral", "Not reviewed"],
    ACCEPTED: ["ok", "Accepted for packet"],
    REJECTED: ["bad", "Rejected"],
    UNRESOLVED: ["warn", "Unresolved"],
  } as const;
  const [tone, label] = map[state];
  return (
    <Badge tone={stale && state !== "UNREVIEWED" ? "warn" : tone} title="Recorded human decision on this claim revision.">
      {label}
      {stale && state !== "UNREVIEWED" ? <span className="font-normal">· basis changed</span> : null}
    </Badge>
  );
}

export function AttentionBadges({ claim }: { claim: Pick<ClaimSummary, "basis_state" | "coverage_state"> }) {
  return (
    <>
      {claim.basis_state === "STALE_SOURCE" ? <Badge tone="warn">Cited source superseded</Badge> : null}
      {claim.coverage_state === "POTENTIAL_NEW_EVIDENCE" ? <Badge tone="info">New document may matter</Badge> : null}
    </>
  );
}

export const ROLE_LABEL: Record<string, string> = {
  supporting: "Supporting",
  qualifying: "Qualifying",
  opposing: "Opposing",
  other: "Other cited",
};

export const REASON_LABEL: Record<string, string> = {
  DIRECT_STATEMENT: "states it directly",
  CONDITIONAL: "adds a condition",
  SUBSEQUENT_CHANGE: "later change",
  DIFFERENT_ENTITY: "different entity",
  DIFFERENT_TIME: "different time",
  NEGATION: "negates it",
  MISSING_DETAIL: "missing detail",
  NOT_RELEVANT: "not relevant",
  AMBIGUOUS: "ambiguous",
};
