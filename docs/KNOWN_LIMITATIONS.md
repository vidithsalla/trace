# Known limitations

What Trace does not do, or does only partially. Kept current with the code.

## Model and inference

- V3 claims and support assessments use a real model through one OpenAI-compatible client:
  `local` (Ollama by default) or `hosted` (explicit egress acknowledgement required). `mock` is a
  deterministic rule set used only when configured, and every run records which one it used.
- The default local model is a 7B model (`qwen2.5:7b-instruct`). It is slow on a laptop
  (tens of seconds per investigation) and weaker than frontier hosted models. Measured numbers
  are in `RESULTS.md`.
- Real-model tests are opt-in (`make test-real-model`, `make eval-v3`) and are not run in CI.
- The V1 workflows under "More tools" (Q&A panel, chronology, entities, contradictions, memos)
  still run on the deterministic legacy engine, labeled `trace-legacy-deterministic`.

## Retrieval and evidence

- V3 retrieval runs in SQL (full-text and pgvector exact search). The V1 search screen still ranks
  vectors in Python over loaded chunks.
- Counterevidence search is lexical (anchor terms plus a fixed list of qualification words) fused
  with semantic neighbours. It is not exhaustive and the UI says so.
- The new-evidence detector (`overlap-v1`) is a lexical overlap heuristic. It can miss relevant
  documents and flag irrelevant ones.
- Spans are sentence-level. Evidence that only makes sense across several sentences is shown as
  several spans.

## Documents

- OCR is disabled by default; scanned PDFs without a text layer produce no passages (the source
  shows a `NO_TEXT_EXTRACTED` warning rather than pretending the document says nothing).
- No layout-aware parsing: tables and multi-column PDFs are flattened. No pixel-level highlight
  in the original PDF; passages are shown as exact normalized text with page numbers.
- Documents that existed before V3 were backfilled from stored page text; when original bytes
  were unavailable their versions are marked `unknown_legacy` instead of given a hash.

## Evaluation

- The V3 evaluation set is small and synthetic (one dispute, 5 end-to-end cases, 18 labeled
  claim/passage pairs), written by the project author. Results show the mechanism and catch
  regressions; they are not a measurement of accuracy on real matters.
- The claim-proposal prompt and schema were revised after observing failures on this same set.
  There is no held-out split yet, so end-to-end numbers are development-set numbers.
- No lawyer or qualified reviewer has validated any output.

## Security and operations

- Local application, not deployed for external users, not audited. See `SECURITY.md`.
- Demo accounts share a known password in development mode.
- Analysis runs are not retried automatically after a worker crash (to avoid silently repeating
  model calls). A run that outlives the job time limit is shown as failed (`worker_lost`) and
  must be re-requested.
