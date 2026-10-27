---
description: Review step N the way a senior teammate would: run the check, read the code and ask questions
argument-hint: <step number 1-7>
---
Review the learner's **step $ARGUMENTS**.

1. Run `make check-$ARGUMENTS` (in step 1, also read `notes/01_findings.md`) and interpret the result.
2. Read the code or models they wrote. Evaluate with the list below and with the "Common traps" and "Comprehension questions" of the file in `guide/` starting with 0$ARGUMENTS.
3. Return the review in this format (friendly but honest):
   - **What is good** (concrete, not generic).
   - **What is wrong or fragile**, with the why and what would happen in production. **Point out the problem, do not write the fix.**
   - **What the check does not verify** but you should look at (quality, clarity, edge cases).
   - **2–3 comprehension questions** for them to answer in their own words.
4. If the step is 1: tell them **how many problem categories** you have seen well documented and which ones (by type, never the exact list) seem to be missing, phrased as questions ("have you compared the beginning and the end of the series?"). Do not reveal the hidden problems.
5. If the check passes and they answered the questions well, say so clearly and suggest the next step; if not, tell them what to reinforce before moving on.

Quick rubric per step: **2** real idempotency, atomic writes, quarantine with a reason, fidelity (nothing cleaned), no hard-coded paths. **3** correct order (time→dedupe), spikes flagged not deleted, units verified, meaningful tests. **4** no leakage, well-defined label, censoring handled, operating state considered. **5** temporal split with purge, suitable metric, no obvious overfitting. **6** declared dependencies, errors not swallowed, no duplicated logic. **7** 404 vs 500, read-only, latest prediction, no SQL injection.
