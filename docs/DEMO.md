# Demo script (3–5 minutes)

Uses the seeded matter **Halden Freight invoice dispute** (synthetic). Sources: an approval memo,
payment terms, a receiving-dock email, and a remittance note that contains a prompt-injection
attempt. The corrected memo (revision 2) lives in
`evals/datasets/conditional-payment-v1/sources/01_approval_memo_v2.txt` for step 6.

1. **Sign in** as `reviewer@trace.local` / `trace-demo-password`. Open the matter.
2. **Investigate**: ask *"Was invoice 7A approved unconditionally on March 18?"* The run pins a
   corpus snapshot, retrieves passages, runs a separate counterevidence search, and proposes
   claims. With the local model this takes roughly 30–60 seconds.
3. **Open a claim.** Point at the three boxes: *Source verified* (code checked the quote exists in
   revision 1), *Conflicting evidence · model* (a suggestion), *Not reviewed* (no human yet).
   The memo's "approved … subject to verification" is a real quote, and the dock email asking to
   hold payment was found by the counterevidence search.
4. **Point at the remittance note.** Its "ignore all previous instructions" text is shown as an
   opposing passage, inert data. Nothing in the run changed a review state.
5. **Accept** the narrow claim with a note. The decision is bound to revision 1 and to the
   evidence digest shown under the button.
6. **Sign in as the attorney** (`attorney@trace.local`), open **Sources**, and upload the corrected
   memo as a new version of `approval memo.txt`. Revision 1 is marked *Superseded*.
7. **Changes** now lists the claim: *Cited source superseded*. The claim page shows
   *Accepted for packet · basis changed*; the decision button refuses to accept against a
   superseded source. Click **Re-check against current sources**: a new revision is created
   against the current snapshot, the decision resets, and history keeps the old acceptance.
8. **Stale tab**: open the same claim in two tabs, record a decision in one, then submit from the
   other. The second gets a clear conflict message instead of overwriting.
9. **Packets**: export the accepted claims. Open `manifest.json` (source versions, evidence
   digests, decision IDs) and `checksums.sha256`. Upload another correction: the old packet does
   not change.
10. **Results**: open `RESULTS.md` for the measured retrieval, counterevidence and support-label
    numbers, including where the local model fails.

Short version (60–90 s): steps 2, 3, 6 and 7.
