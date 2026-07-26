# Case Study — A Self-Serve Analyst on Top of the Churn Model

**The continuation.** Project 3 gave a sporting director a retention model and
a dashboard. The follow-up question was immediate: "can I just *ask* it
things?" This project is that answer — a natural-language agent that turns
plain-English questions ("which position group has the highest churn rate?",
"show players paid above their squad's median wage with churn risk over 70%")
into SQL, runs it against Project 3's real DuckDB database, and shows the
result *with the query that produced it* — verifiable, not vibes.

**The engineering is the guardrails.** The LLM (Gemini, structured output)
only ever drafts; code decides. Five layers: prompt rules, a single-statement
SELECT-only shape check, a keyword denylist (DROP/DELETE/ATTACH/COPY/…),
DuckDB's own `EXPLAIN` binding every table and column before execution — so a
hallucinated column returns "couldn't verify this query is safe," never a
guess — and a read-only connection underneath, so even a total bypass cannot
write. Row caps and timeouts contain runaway queries.

**Tested, not asserted.** An 18-question eval — analytical, prompt-injection,
ambiguous, and impossible questions — runs against the live agent: 3/3
injections refused, the nonexistent-data question honestly declined, and both
ambiguous questions answered with a clarifying question instead of a silent
guess (a behavior that took a documented prompt iteration to get right). The
result is the portfolio's thesis in one tool: AI that's useful because it
knows exactly what it's allowed to do — and says so when it doesn't.
