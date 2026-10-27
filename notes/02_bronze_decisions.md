# Step 2 — My design decisions for bronze

> Answer in your own words, a few lines per question. There is no single correct answer: what matters is that you can
> **defend** what you chose. These questions are asked as they are in data engineering interviews.
> Replace every `TODO-STUDENT`.

1. **How does your ingestion know that a file was already loaded?** What would happen if the same file changes later (the
   provider corrects it)? Would your design detect it?

TODO-STUDENT

2. **Why Parquet and not leave the CSVs? Why not clean already in bronze?**

TODO-STUDENT

3. **What happens if your process dies halfway through writing a file?** How did you avoid leaving a half-written Parquet?

TODO-STUDENT

4. **What did you do with the corrupt file and why did you not simply ignore it?** Who should find out, and how?

TODO-STUDENT

5. **What metadata did you add to each row and what is it for when someone asks "where did this number come from"?**

TODO-STUDENT
