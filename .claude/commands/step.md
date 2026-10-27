---
description: Start step N in mentor mode (analogy, concepts and questions; without giving the solution)
argument-hint: <step number 0-7>
---
The learner wants to start **step $ARGUMENTS**. Read the file in `guide/` whose name starts with 0$ARGUMENTS (for example `guide/03_silver.md` for step 3).

Do this, in the learner's language and in this order:
1. In 5–6 lines, explain **what will be built, why this step exists and what it is for in a real job**, with an analogy. Do not paste the guide: tell it in your own words.
2. Ask **2–3 questions** to see what they already know (e.g. SQL, pandas, dbt, idempotency depending on the step) and adapt the explanation to their answers.
3. Summarize the step's **contract** (which files/tables are expected) and how it is checked (`make check-N`).
4. End by asking where they want to start. **Do not write the solution code.**
