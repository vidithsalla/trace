"""V3 evaluation harness (PRD section 10). Stage metrics, never one blended score.

    python -m app.scripts.eval_v3 --engines mock,local --profiles all

Stages:
  retrieval        span-level recall/MRR/char-F1 per retrieval profile (model-independent)
  counterevidence  opposing-span recall with vs without the challenge pass
  relation         support classifier on human-labeled (claim, passage) pairs, confusion matrix
  end_to_end       full pipeline per engine: status, gate integrity, labels, latency, tokens
  drift            deterministic stale-source detection and coverage-alert false alarms

Everything runs in a throwaway organization that is deleted afterwards. Unknown manifest
values are recorded as null, never invented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.claims import Claim, ClaimRevision
from app.models.domain import Matter, MatterMember, Organization, User
from app.models.evidence import ExtractionPage, ExtractionVersion, SourceSpan
from app.scripts.seed_v3_demo import dataset_dir
from app.services import retrieval_v3
from app.services.analysis import execute_analysis, start_analysis
from app.services.change_control import ReviewRequest, submit_review
from app.services.embeddings import OllamaEmbeddingClient
from app.services.eval_validation import assert_valid_dataset, validate_profiles
from app.services.evidence_versions import create_snapshot, write_embeddings
from app.services.llm.client import CallBudget, LLMError, ProviderConfig
from app.services.llm.contracts import EvidencePack, EvidencePackItem
from app.services.llm.engine import MockClaimEngine, RealClaimEngine
from app.services.parsers import normalize_text
from app.services.text_ingest import ingest_text_document

ALL_PROFILES = list(retrieval_v3.PROFILES)
SCORING_VERSION = "trace-eval-v3.1"


# ---------------------------------------------------------------------------------------------
def build_engine(name: str):
    if name == "mock":
        return MockClaimEngine()
    if name == "local":
        from app.services.llm.client import ChatClient

        return RealClaimEngine(ChatClient(ProviderConfig(
            kind="local", model=settings.model_name, base_url=settings.model_base_url,
            timeout_seconds=float(settings.model_timeout_seconds), max_retries=1)))
    raise SystemExit(f"unknown engine {name}")


class World:
    def __init__(self, db, root: Path, manifest: dict):
        self.db, self.root, self.manifest = db, root, manifest
        suffix = uuid.uuid4().hex[:8]
        self.org = Organization(name=f"Trace eval {suffix}", slug=f"trace-eval-{suffix}")
        db.add(self.org)
        db.flush()
        self.user = User(organization_id=self.org.id, email=f"eval-{suffix}@trace.local", name="Eval",
                         global_role="member", password_hash=hash_password(uuid.uuid4().hex))
        db.add(self.user)
        db.flush()

    def matter(self, *, revisions=(1,), extra: dict[str, str] | None = None, semantic=False):
        m = Matter(organization_id=self.org.id, name=f"eval {uuid.uuid4().hex[:6]}",
                   matter_code=uuid.uuid4().hex[:10], created_by=self.user.id)
        self.db.add(m)
        self.db.flush()
        self.db.add(MatterMember(matter_id=m.id, user_id=self.user.id, role="reviewer"))
        docs = {}
        for source in sorted(self.manifest["sources"], key=lambda s: s["revision"]):
            if source["revision"] not in revisions and source["revision"] != 1:
                continue
            body = (self.root / "sources" / source["file"]).read_text()
            docs[source["document"]] = ingest_text_document(
                self.db, m, self.user, source["document"] + ".txt", body,
                document=docs.get(source["document"]))
        for name, body in (extra or {}).items():
            docs[name] = ingest_text_document(self.db, m, self.user, name + ".txt", body)
        if semantic:
            spans = self.db.scalars(select(SourceSpan).where(SourceSpan.matter_id == m.id)).all()
            write_embeddings(self.db, spans, OllamaEmbeddingClient(settings.embedding_base_url,
                                                                   settings.embedding_ollama_model))
        self.db.commit()
        return m, docs

    def cleanup(self):
        self.db.rollback()
        self.db.execute(delete(Matter).where(Matter.organization_id == self.org.id))
        self.db.execute(delete(Organization).where(Organization.id == self.org.id))
        self.db.commit()


def gold_ranges(db, matter, docs, golds) -> list[tuple]:
    """Map each gold quote to (extraction_version_id, page, start, end) in the current version."""
    out = []
    for gold in golds:
        document = docs[gold["document"]]
        db.refresh(document)
        page = db.scalar(select(ExtractionPage).join(
            ExtractionVersion, ExtractionVersion.id == ExtractionPage.extraction_version_id).where(
            ExtractionVersion.document_version_id == document.current_version_id))
        quote = normalize_text(gold["quote"])
        start = page.text.find(quote)
        if start < 0:
            raise RuntimeError(f"gold quote not found: {gold['quote'][:40]}")
        out.append((page.extraction_version_id, page.page_no, start, start + len(quote)))
    return out


def _overlap(a, b) -> int:
    if a[0] != b[0] or a[1] != b[1]:
        return 0
    return max(0, min(a[3], b[3]) - max(a[2], b[2]))


def span_range(db, span_id) -> tuple:
    s = db.get(SourceSpan, span_id)
    return (s.extraction_version_id, s.page_no, s.normalized_start, s.normalized_end)


# ---------------------------------------------------------------------------------------------
def eval_retrieval(world: World, profiles: list[str], k: int) -> dict:
    db, manifest = world.db, world.manifest
    semantic_needed = any(retrieval_v3.PROFILES[p]["semantic"] == "minilm-l6-v2-ollama" for p in profiles)
    matter, docs = world.matter(semantic=semantic_needed)
    snapshot = create_snapshot(db, matter.id, world.user.id)
    db.commit()
    cases = [c for c in manifest["cases"] if c.get("gold_supporting") or c.get("gold_opposing")]
    results = {}
    for profile in profiles:
        rows, latencies = [], []
        for case in cases:
            golds = gold_ranges(db, matter, docs, case.get("gold_supporting", []) + case.get("gold_opposing", []))
            started = time.perf_counter()
            cands = retrieval_v3.retrieve(db, matter_id=matter.id, snapshot_id=snapshot.id,
                                          query=case["question"], profile=profile, k=k)
            latencies.append((time.perf_counter() - started) * 1000)
            ranges = [span_range(db, c.source_span_id) for c in cands]
            hit_ranks = [i + 1 for i, r in enumerate(ranges) if any(_overlap(r, g) for g in golds)]
            covered = sum(1 for g in golds if any(_overlap(r, g) for r in ranges))
            inter = sum(max((_overlap(r, g) for r in ranges), default=0) for g in golds)
            retrieved_chars = sum(r[3] - r[2] for r in ranges) or 1
            gold_chars = sum(g[3] - g[2] for g in golds) or 1
            rows.append({"case_id": case["case_id"], "hit": bool(hit_ranks),
                         "first_hit_rank": hit_ranks[0] if hit_ranks else None,
                         "gold_spans": len(golds), "gold_spans_retrieved": covered,
                         "char_precision": inter / retrieved_chars, "char_recall": inter / gold_chars})
        n = len(rows)
        p = sum(r["char_precision"] for r in rows) / n
        r_ = sum(r["char_recall"] for r in rows) / n
        results[profile] = {
            "n_queries": n, "k": k,
            "recall_at_k": sum(r["hit"] for r in rows) / n,
            "gold_span_recall_at_k": sum(r["gold_spans_retrieved"] for r in rows) / sum(r["gold_spans"] for r in rows),
            "mrr_at_k": sum(1 / r["first_hit_rank"] if r["first_hit_rank"] else 0 for r in rows) / n,
            "char_precision": p, "char_recall": r_, "char_f1": 2 * p * r_ / (p + r_) if p + r_ else 0.0,
            "p50_ms": sorted(latencies)[len(latencies) // 2], "per_query": rows,
        }
    return results


def eval_counterevidence(world: World, profiles: list[str]) -> dict:
    db, manifest = world.db, world.manifest
    semantic_needed = any(retrieval_v3.PROFILES[p]["semantic"] == "minilm-l6-v2-ollama" for p in profiles)
    matter, docs = world.matter(semantic=semantic_needed)
    snapshot = create_snapshot(db, matter.id, world.user.id)
    db.commit()
    cases = [c for c in manifest["cases"] if c.get("gold_opposing") and c.get("claim")]
    out = {}
    for profile in profiles:
        with_pass = without = total = 0
        rows = []
        for case in cases:
            golds = gold_ranges(db, matter, docs, case["gold_opposing"])
            primary = retrieval_v3.retrieve(db, matter_id=matter.id, snapshot_id=snapshot.id,
                                            query=case["question"], profile=profile, k=8)
            counter = retrieval_v3.counterevidence(db, matter_id=matter.id, snapshot_id=snapshot.id,
                                                   claim=case["claim"], profile=profile, k=6)
            # Mirrors the assessment pack: top primary passages plus counterevidence.
            base = [span_range(db, c.source_span_id) for c in primary[:4]]
            both = base + [span_range(db, c.source_span_id) for c in counter]
            found_base = sum(1 for g in golds if any(_overlap(r, g) for r in base))
            found_both = sum(1 for g in golds if any(_overlap(r, g) for r in both))
            total += len(golds)
            without += found_base
            with_pass += found_both
            rows.append({"case_id": case["case_id"], "gold_opposing": len(golds),
                         "found_without_pass": found_base, "found_with_pass": found_both})
        out[profile] = {"n_cases": len(cases), "n_opposing_spans": total,
                        "opposing_recall_without_pass": without / total if total else None,
                        "opposing_recall_with_pass": with_pass / total if total else None,
                        "per_case": rows}
    return out


def eval_relations(world: World, engine) -> dict:
    labels = ["supports", "qualifies", "contradicts", "irrelevant", "uncertain"]
    matrix = defaultdict(Counter)
    rows, errors, calls = [], Counter(), []
    for pair in world.manifest["relation_pairs"]:
        item = EvidencePackItem(ref="ev_01", source_span_id=None, chunk_id=None, document_id=uuid.uuid4(),
                                document_title=pair["document"].replace("_", " "), page=1,
                                text=normalize_text(pair["quote"]))
        budget = CallBudget(2)
        try:
            assessment = engine.assess_support(pair["claim"], EvidencePack((item,)), budget)
            predicted = next((r.relation for r in assessment.relations if r.evidence_ref == "ev_01"), "uncertain")
        except LLMError as exc:
            predicted = "error"
            errors[exc.code] += 1
        calls += [r.as_dict() for r in budget.records]
        matrix[pair["gold_relation"]][predicted] += 1
        rows.append({"pair_id": pair["pair_id"], "gold": pair["gold_relation"], "predicted": predicted})
    n = len(rows)
    per_class = {}
    for label in labels[:4]:
        tp = matrix[label][label]
        pred = sum(matrix[g][label] for g in matrix)
        gold = sum(matrix[label].values())
        per_class[label] = {"precision": tp / pred if pred else None, "recall": tp / gold if gold else None,
                            "n_gold": gold}
    unsafe = sum(1 for r in rows if r["predicted"] == "supports" and r["gold"] != "supports")
    non_support_gold = sum(1 for r in rows if r["gold"] != "supports")
    return {"n_pairs": n, "accuracy": sum(r["gold"] == r["predicted"] for r in rows) / n,
            "unsafe_support_rate": unsafe / non_support_gold if non_support_gold else None,
            "unsafe_support_count": unsafe, "errors": dict(errors),
            "confusion": {g: dict(c) for g, c in matrix.items()}, "per_class": per_class,
            "latency_ms_p50": _p(calls, 50), "latency_ms_p95": _p(calls, 95),
            "tokens": _tokens(calls), "per_pair": rows}


def eval_end_to_end(world: World, engine, profile: str) -> dict:
    db = world.db
    matter, _ = world.matter(semantic=retrieval_v3.PROFILES[profile]["semantic"] == "minilm-l6-v2-ollama")
    rows, calls = [], []
    for case in world.manifest["cases"]:
        if case["failure_mode"] == "stale_source":
            continue
        run, _ = start_analysis(db, matter_id=matter.id, user_id=world.user.id, question=case["question"],
                                profile=profile, idempotency_key=f"eval-{uuid.uuid4().hex}")
        db.commit()
        started = time.perf_counter()
        run = execute_analysis(db, run.id, engine=engine)
        elapsed = (time.perf_counter() - started) * 1000
        calls += run.call_records
        claims = []
        for claim in db.scalars(select(Claim).where(Claim.run_id == run.id)):
            rev = db.get(ClaimRevision, (claim.id, 1))
            claims.append({"text": rev.text, "gate": rev.source_gate_state, "gate_reasons": rev.source_gate_reasons,
                           "candidate": rev.relation_candidate, "review_state": claim.review_state})
        row = {"case_id": case["case_id"], "failure_mode": case["failure_mode"], "status": run.status,
               "error_code": run.error_code, "elapsed_ms": round(elapsed), "claims": claims,
               "gold_relation": case.get("gold_relation")}
        flags = []
        if case.get("gold_relation") == "not_established" and run.status == "COMPLETED" and any(
                c["candidate"] == "SUPPORT_CANDIDATE" for c in claims):
            flags.append("answered_unanswerable_with_support")
        if case["failure_mode"] == "prompt_injection" and any(
                c["candidate"] == "SUPPORT_CANDIDATE" and "uncondition" in c["text"].lower() for c in claims):
            flags.append("injected_assertion_supported")
        if any(c["review_state"] != "UNREVIEWED" for c in claims):
            flags.append("review_state_changed_without_human")
        row["flags"] = flags
        rows.append(row)
    all_claims = [c for r in rows for c in r["claims"]]
    return {
        "profile": profile, "n_cases": len(rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "n_claims": len(all_claims),
        "gate_verified_rate": (sum(c["gate"] == "VERIFIED" for c in all_claims) / len(all_claims)) if all_claims else None,
        "candidate_counts": dict(Counter(c["candidate"] for c in all_claims)),
        "flagged_cases": [r["case_id"] for r in rows if r["flags"]],
        "latency_ms_p50": _p(calls, 50), "latency_ms_p95": _p(calls, 95), "tokens": _tokens(calls),
        "per_case": rows,
    }


def eval_drift(world: World) -> dict:
    db, manifest = world.db, world.manifest
    matter, docs = world.matter()
    engine = MockClaimEngine()
    run, _ = start_analysis(db, matter_id=matter.id, user_id=world.user.id,
                            question="Was invoice 7A approved subject to verification of delivery receipts?",
                            profile="hash_hybrid_baseline", idempotency_key=f"drift-{uuid.uuid4().hex}")
    db.commit()
    execute_analysis(db, run.id, engine=engine)
    claims = db.scalars(select(Claim).where(Claim.run_id == run.id)).all()
    for claim in claims:
        rev = db.get(ClaimRevision, (claim.id, 1))
        if rev.source_gate_state == "VERIFIED":
            submit_review(db, matter_id=matter.id, claim_id=claim.id, actor_id=world.user.id,
                          idempotency_key=uuid.uuid4().hex,
                          request=ReviewRequest("accept", 1, rev.evidence_set_sha256, 0, "SOURCE_REVIEWED", None))
    db.commit()
    reviewed = [c for c in claims if c.review_state == "ACCEPTED"]
    cites_memo = []
    for c in reviewed:
        cited = db.execute(text("""SELECT count(*) FROM claim_evidence ce JOIN source_spans s ON s.id = ce.source_span_id
                                   WHERE ce.claim_id = :c AND s.document_id = :d"""),
                           {"c": c.id, "d": docs["approval_memo"].id}).scalar_one()
        if cited:
            cites_memo.append(c.id)

    unrelated = ingest_text_document(db, matter, world.user, "cafeteria.txt",
                                     "The cafeteria menu for Friday includes soup and sandwiches.")
    db.commit()
    false_alarms = sum(1 for c in reviewed if db.get(Claim, c.id).coverage_state != "CURRENT")
    v2 = next(s for s in manifest["sources"] if s["document"] == "approval_memo" and s["revision"] == 2)
    ingest_text_document(db, matter, world.user, "approval_memo.txt",
                         (world.root / "sources" / v2["file"]).read_text(), document=docs["approval_memo"])
    db.commit()
    detected = sum(1 for cid in cites_memo if db.get(Claim, cid).basis_state == "STALE_SOURCE")
    assert unrelated
    return {"accepted_claims": len(reviewed), "claims_citing_changed_source": len(cites_memo),
            "stale_source_detected": detected,
            "stale_detection_rate": detected / len(cites_memo) if cites_memo else None,
            "unrelated_document_false_alarms": false_alarms,
            "note": "Deterministic detector; tiny scenario count. Demonstrates the mechanism, not a rate."}


def _p(calls, pct):
    values = sorted(c["latency_ms"] for c in calls if c.get("status") == "ok")
    return values[min(len(values) - 1, int(len(values) * pct / 100))] if values else None


def _tokens(calls):
    prompt = [c["prompt_tokens"] for c in calls if c.get("prompt_tokens")]
    completion = [c["completion_tokens"] for c in calls if c.get("completion_tokens")]
    return {"calls": len(calls), "prompt_total": sum(prompt) if prompt else None,
            "completion_total": sum(completion) if completion else None}


# ---------------------------------------------------------------------------------------------
def dataset_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted([root / "manifest.json", *sorted((root / "sources").iterdir())]):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def runtime_info(db) -> dict:
    info = {"python": platform.python_version(),
            "postgres": db.execute(text("SHOW server_version")).scalar_one(), "ollama": None}
    try:
        import httpx

        base = settings.model_base_url.rsplit("/v1", 1)[0]
        info["ollama"] = httpx.get(f"{base}/api/version", timeout=3).json().get("version")
    except Exception:  # noqa: BLE001 - optional: unknown stays null
        pass
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engines", default="mock")
    parser.add_argument("--profiles", default="lexical_v1,hash_hybrid_baseline")
    parser.add_argument("--e2e-profile", default=None)
    parser.add_argument("--out", default="/app/evals/reports")
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()
    profiles = ALL_PROFILES if args.profiles == "all" else args.profiles.split(",")
    engines = args.engines.split(",")
    root = dataset_dir()
    manifest = json.loads((root / "manifest.json").read_text())
    assert_valid_dataset(manifest, root / "sources")  # EVAL-01: refuse to score a broken/leaky set
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + settings.code_commit[:7]
    out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        bad_profiles = validate_profiles(db, {p: retrieval_v3.PROFILES[p] for p in profiles})
        if bad_profiles:  # EVAL-02: never report hash vectors as a semantic experiment
            raise SystemExit("; ".join(bad_profiles))
        world = World(db, root, manifest)
        try:
            results = {"retrieval": eval_retrieval(world, profiles, args.k),
                       "counterevidence": eval_counterevidence(world, profiles),
                       "relation": {}, "end_to_end": {}, "drift": eval_drift(world)}
            e2e_profile = args.e2e_profile or ("semantic_hybrid_v2" if "semantic_hybrid_v2" in profiles
                                               else profiles[-1])
            for name in engines:
                engine = build_engine(name)
                results["relation"][name] = eval_relations(world, engine)
                results["end_to_end"][name] = eval_end_to_end(world, engine, e2e_profile)
            run_manifest = {
                "run_id": run_id, "scoring_version": SCORING_VERSION, "code_sha": settings.code_commit,
                "dataset_id": manifest["dataset_id"], "dataset_sha256": dataset_digest(root),
                "label_author": manifest.get("label_author"), "retrieval_profiles": profiles,
                "end_to_end_profile": e2e_profile, "k": args.k,
                "engines": {n: (build_engine(n).describe()) for n in engines},
                "embedding_profiles": sorted({retrieval_v3.PROFILES[p]["semantic"] for p in profiles} - {None}),
                "runtime": runtime_info(db), "started_at": run_id[:16],
            }
        finally:
            world.cleanup()

    (out_dir / "manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(json.dumps({"out": str(out_dir), "retrieval": {p: {k: v for k, v in m.items() if k != "per_query"}
                                                         for p, m in results["retrieval"].items()},
                      "counterevidence": {p: {k: v for k, v in m.items() if k != "per_case"}
                                          for p, m in results["counterevidence"].items()},
                      "relation": {e: {k: v for k, v in m.items() if k not in ("per_pair",)}
                                   for e, m in results["relation"].items()},
                      "end_to_end": {e: {k: v for k, v in m.items() if k != "per_case"}
                                     for e, m in results["end_to_end"].items()},
                      "drift": results["drift"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
