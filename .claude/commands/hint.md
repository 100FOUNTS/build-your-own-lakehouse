---
description: Give the NEXT hint for step N, from less to more help, without giving away the solution
argument-hint: <step number 1-7>
---
The learner is stuck on **step $ARGUMENTS**. Read that step's guide (the file in `guide/` starting with 0$ARGUMENTS) and their current code.

1. Ask (if they did not say) **what they have tried** and what result/error they got. If they already told you, do not repeat the question.
2. Diagnose where the real obstacle is (missing concept, misreading, bug).
3. Give **a single hint**, at the lowest level that helps: first a question that makes them look in the right direction; if they already tried that, the hint from the guide; only as a last resort, a minimal example with toy data (not the exact solution code).
4. Ask them to try it and come back with the result. Do not solve the step.
