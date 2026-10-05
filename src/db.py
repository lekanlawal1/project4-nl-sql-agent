"""Read-only database layer: connection, schema introspection, capped execution.

Defense in depth starts here: the DuckDB connection itself is opened
read_only=True, so even if every other guardrail failed, a write statement
dies at the engine — safety enforced by the database, not by a prompt.
"""

import os
import threading
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
# Default: the committed snapshot (see scripts/make_snapshot.py). Point DB_PATH
# at Project 3's live churn.duckdb to query it directly instead.
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "data" / "churn_agent.duckdb"))

ROW_CAP = 200          # answers are for reading, not exporting
TIMEOUT_S = 10         # runaway-query ceiling

# Hand-written data dictionary: introspection gives names/types; this gives
# meaning. Both are fed to the model — names alone invite wrong guesses about
# semantics (e.g. churned=1 means LEFT, not stayed).
DESCRIPTIONS = {
    "features": "One row per player present in both FIFA editions (the modeling table). "
                "churned=1 means the player LEFT their club between FIFA 18 and FIFA 19.",
    "labeled": "Same players as features but with all 34 detailed skill ratings "
               "(dribbling, finishing, gk_reflexes, ...). Also has churned.",
    "club_mapping": "Entity-resolution map: FIFA 18 club name -> canonical FIFA 19 club name.",
    "model_scores": "Out-of-fold churn-risk probability (0-1) per player from Project 3's "
                    "gradient-boosting model.",
    "players_scored": "PREFER THIS VIEW for risk questions: features joined with each "
                      "player's churn_risk probability (0-1).",
}


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def introspect(con) -> str:
    """Render the live schema as prompt text. Called fresh at startup — the
    model never works from a remembered or hand-maintained schema."""
    lines = []
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables ORDER BY table_name").fetchall()]
    for t in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", [t]).fetchall()
        desc = DESCRIPTIONS.get(t, "")
        lines.append(f"TABLE {t} — {desc}")
        lines.append("  " + ", ".join(f"{c} {d}" for c, d in cols))
    # Category values the model would otherwise guess at
    for t, c in [("features", "position_group"), ("features", "age_band")]:
        vals = [r[0] for r in con.execute(
            f"SELECT DISTINCT {c} FROM {t} ORDER BY 1").fetchall()]
        lines.append(f"VALUES {t}.{c}: {', '.join(map(str, vals))}")
    return "\n".join(lines)


def known_identifiers(con) -> set[str]:
    ids = set()
    for t, c in con.execute(
            "SELECT table_name, column_name FROM information_schema.columns").fetchall():
        ids.add(t.lower())
        ids.add(c.lower())
    return ids


def run_capped(con, sql: str):
    """Execute with a row cap and a hard timeout.

    Returns (columns, rows, truncated). The cap is applied by wrapping, so it
    holds regardless of what LIMIT the model wrote. Timeout is enforced with
    con.interrupt() from a watchdog thread — DuckDB has no statement_timeout.
    """
    wrapped = f"SELECT * FROM ({sql.rstrip(';')}) LIMIT {ROW_CAP + 1}"
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        cur = con.execute(wrapped)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    finally:
        timer.cancel()
    truncated = len(rows) > ROW_CAP
    return cols, rows[:ROW_CAP], truncated
