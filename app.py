"""Streamlit demo: ask the churn database a question in plain English.

Same stack as Project 2's demo on purpose — one language across the
portfolio, free GitHub-integrated hosting, secrets manager for the API key.
Every answer shows the SQL that actually ran: verifiable, not vibes.
"""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent / "src"))
import db  # noqa: E402
from agent import Agent  # noqa: E402

st.set_page_config(page_title="Churn Analyst Agent", layout="centered")

st.title("Ask the Churn Database")
st.caption(
    "Plain-English questions, answered with real SQL against the FIFA player-churn "
    "database from [Project 3](https://github.com/lekanlawal1/project3-player-churn). "
    "Read-only by construction; every answer shows the query it ran. "
    "[Source & guardrail docs](https://github.com/lekanlawal1/project4-nl-sql-agent)")

EXAMPLES = [
    "Which position group has the highest churn rate?",
    "Show players paid above their squad's median wage with churn risk over 70%",
    "Top 10 clubs by number of players who left",
    "What's the average churn risk by age band?",
    "Which of the 20 best dribblers actually left their club?",
]


def get_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except FileNotFoundError:
        pass
    return os.environ.get("GEMINI_API_KEY")


@st.cache_resource
def get_agent():
    con = db.connect()
    return Agent(con, db.introspect(con), api_key=get_api_key())


example = st.selectbox("Try an example question", ["— or type your own below —"] + EXAMPLES)
question = st.text_input("Your question",
                         value="" if example.startswith("—") else example)

if st.button("Ask", type="primary", disabled=not question.strip()):
    if not get_api_key():
        st.error("No `GEMINI_API_KEY` configured. Locally: copy `.env.example` to `.env`. "
                 "On Streamlit Cloud: App settings → Secrets.")
        st.stop()
    with st.spinner("Translating to SQL and running it…"):
        r = get_agent().ask(question.strip())

    if r["status"] == "answered":
        st.markdown(f"**What was computed:** {r['explanation']}")
        st.dataframe(r["rows"], column_config=None, width="stretch",
                     hide_index=True) if not r["columns"] else st.dataframe(
            {c: [row[i] for row in r["rows"]] for i, c in enumerate(r["columns"])},
            width="stretch", hide_index=True)
        if r["truncated"]:
            st.caption(f"Showing the first {r['row_cap']} rows (hard cap).")
        st.markdown("**SQL that ran** (read-only connection, "
                    f"{r['timeout_s']}s timeout, {r['row_cap']}-row cap):")
        st.code(r["sql"], language="sql")
    elif r["status"] == "clarify":
        st.warning(f"**Quick clarification needed:** {r['clarifying_question']}")
        if r["explanation"]:
            st.caption(r["explanation"])
    elif r["status"] == "refused":
        st.info(f"**Can't answer that one:** {r['explanation']}")
    elif r["status"] == "blocked":
        st.error(f"**Query blocked by guardrails:** {r['detail']}")
        if r["sql"]:
            st.code(r["sql"], language="sql")
        st.caption("The generated SQL failed a safety check, so it never touched the "
                   "database. This is the system working as designed.")
    else:
        st.error(f"**Something went wrong:** {r['detail']}")
        st.caption("The failure was contained — no partial or unverified result was shown.")

with st.expander("How this stays safe"):
    st.markdown("""
- **Read-only connection** — writes are impossible at the database-engine level, before any other check.
- **Schema grounding** — the live schema is introspected at startup and injected into every prompt; the model never works from memory.
- **Code-enforced validation** — one statement, SELECT-only, keyword denylist (DROP/DELETE/ATTACH/COPY/…), then DuckDB's own `EXPLAIN` verifies every table and column exists *before* execution. A hallucinated column returns "couldn't verify this query is safe," not a guess.
- **Caps** — 10-second timeout, 200-row limit, both enforced in code.
- **Honest uncertainty** — ambiguous questions get a clarifying question back; unanswerable ones get a refusal with the reason. Real examples of each: see `docs/guardrails.md`.
""")
