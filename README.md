# NL→SQL Analyst Agent — Ask the Churn Database in Plain English

**Live demo:** _deploying — link coming after Streamlit Cloud setup_ · **Stack:** Python · Gemini (structured output) · DuckDB · Streamlit

## Problem statement

Project 3 built a player-churn database and model; the natural next ask from its sporting-director audience is self-serve: *"which positions have the highest churn risk?"* without filing a ticket to an analyst. Text-to-SQL is easy to demo and hard to trust — models hallucinate columns, run anything they're asked to, and guess silently when questions are vague. This project is the trust engineering: an agent that translates plain English into SQL against **Project 3's real DuckDB database**, and is *provably read-only, schema-grounded, and honest about uncertainty*.

## My approach

1. **Schema grounding** ([src/db.py](src/db.py)): the live schema is introspected from `information_schema` at startup — plus a hand-written data dictionary (structure from introspection, *meaning* from documentation: the model must be told `churned=1` means left) and enumerated category values. Injected into every prompt; the model never works from memory.
2. **Constrained generation** ([src/agent.py](src/agent.py)): Gemini with a structured `response_schema` returns `{action: run_sql | clarify | cannot_answer, sql, explanation, clarifying_question}` — SQL as a field, never parsed out of prose. One self-correction retry on binder/execution errors; a second failure is reported honestly.
3. **Guardrails in code** ([src/guardrails.py](src/guardrails.py)): single-statement SELECT-only shape check → keyword denylist → **DuckDB `EXPLAIN` plan check** that binds every table/column *before execution* (hallucinated identifiers return "couldn't verify this query is safe") → read-only connection → 200-row cap and 10-second timeout. Documented with real catches in [docs/guardrails.md](docs/guardrails.md).
4. **Explainability** ([app.py](app.py)): every answer shows the SQL that ran and a one-sentence plain-English restatement of what was computed.
5. **Evaluation** ([tests/run_eval.py](tests/run_eval.py)): 18 questions — 12 analytical, 3 prompt-injections, 2 ambiguous, 1 impossible — run live, transcript committed ([docs/eval_transcript.md](docs/eval_transcript.md)).

## Key decisions and why

- **Read-only enforced in code, not prompting** — a prompt is a request; code is a boundary. Injected text can steer what the model emits; it cannot change what `validate()` returns or make a `read_only=True` connection write. In the eval the model refused all three injections at the prompt layer anyway — the code layers exist so nothing depends on that.
- **DuckDB's `EXPLAIN` as the existence check** — instead of half-reimplementing a SQL parser with regex, the database's own binder verifies every identifier without executing. Exact, free, and impossible to drift out of sync with the real schema.
- **Built on Project 3, not a fifth dataset** — the portfolio tells one story: pipeline → model → dashboard → self-serve agent, all on the same data. The agent queries a snapshot built by [scripts/make_snapshot.py](scripts/make_snapshot.py) from Project 3's DB (verbatim table copies + the dashboard's out-of-fold risk scores as a `model_scores` table), because Project 3's `.duckdb` is git-ignored and a cloud deploy can't read a laptop file. Set `DB_PATH` to point at Project 3's live DB directly.
- **Gemini + Streamlit reused from Project 2** — one consistent integration pattern across the portfolio (structured output, `.env` key handling, Streamlit Cloud secrets). Model note, same saga as Project 2: the free-tier 2.5 Flash is retired; this uses `gemini-3-flash-preview`.
- **The ambiguity dial set by measurement** — v1 of the prompt allowed disclosed defaults and silently answered both ambiguous test questions; v2 restricts defaults to *presentation* (limits, ordering), never *definition* ("risky", "underpaid" → clarifying question with 2–3 concrete interpretations). Cost: one borderline normal question now over-asks. Chosen deliberately: over-asking beats over-assuming in a tool whose product is trust. Full iteration: [docs/prompt_engineering.md](docs/prompt_engineering.md).

## Results (18-question live eval)

| Category | Outcome |
|---|---|
| Analytical (12) | 11 answered with SQL + explanation; 1 asked a reasonable clarifying question |
| Prompt injection (3) | **3/3 refused** — including fake-admin framing; code layers never even needed |
| Ambiguous (2) | **2/2 clarified** instead of silently guessing (after v2 prompt fix) |
| Nonexistent data (1) | honest refusal naming what the schema lacks |

## Free-tier caveat (same style as Project 2)

Brand-new Gemini API keys currently get ~20 requests/day until billing is attached; one eval run is ~20 calls. With a billed key this whole project's API usage costs pennies. If the demo returns quota errors, that's the key, not the code.

## Repo structure

```
data/churn_agent.duckdb   committed snapshot of Project 3's DB (see scripts/make_snapshot.py)
scripts/make_snapshot.py  rebuilds the snapshot from Project 3's pipeline output
src/db.py                 read-only connection · schema introspection · row cap · timeout
src/guardrails.py         shape check · denylist · EXPLAIN plan check
src/agent.py              grounded prompt · structured output · self-correction retry
app.py                    Streamlit demo (answer + SQL + explanation)
tests/run_eval.py         the 18-question eval (regenerates docs/eval_transcript.md)
docs/                     guardrails.md · prompt_engineering.md · eval_transcript.md · case_study.md
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                        # add your Gemini key
.venv/bin/python tests/run_eval.py          # optional: rerun the 18-question eval
.venv/bin/streamlit run app.py              # local demo
```

To rebuild the data snapshot from source instead of using the committed one: run Project 3's pipeline first (`cd ../project3-player-churn && python src/run_pipeline.py`), then `python scripts/make_snapshot.py`.
