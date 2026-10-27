# Step 7 — My design decisions for the API

> Answer in your own words. Replace every `TODO-STUDENT`.

1. **Why `404` and not `500` for an unknown pump? Who is harmed by a 500?**

TODO-STUDENT

2. **What would happen if the API opened the database in write mode and the pipeline ran at 6:00? And if it does so in read-only mode?**

TODO-STUDENT

3. **Today the API reads a table written by the pipeline. What happens if the pipeline fails and the table is from yesterday? How would whoever consumes the API notice?** (Hint: what is `as_of` for?)

TODO-STUDENT

4. **What would you change if the API received 1000 requests per second?**

TODO-STUDENT

5. **What sensitive information could leak through an error message?**

TODO-STUDENT
