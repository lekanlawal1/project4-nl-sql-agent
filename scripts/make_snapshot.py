"""Build data/churn_agent.duckdb — the deployable snapshot of Project 3's database.

Why a snapshot exists at all: Project 3's churn.duckdb is (correctly) gitignored
and only materializes by running that project's pipeline, but a cloud-deployed
agent can't reach a file on a laptop. This script copies the three analytical
tables the agent needs, verbatim, from Project 3's DB — no re-cleaning, no
re-modeling — and adds one table Project 3 publishes outside the DB:

  model_scores — the out-of-fold churn-risk scores from Project 3's dashboard
  export (dashboard/data.js). Those are real Project 3 outputs (5-fold
  cross_val_predict); importing them makes "high churn score" questions
  answerable. They are joined on (name, club, age, overall); the handful of
  composite-key collisions are dropped and reported rather than guessed at.

Run AFTER Project 3's pipeline has produced its DB:
    python scripts/make_snapshot.py
"""

import json
import re
import sys
from pathlib import Path

import duckdb

P4 = Path(__file__).resolve().parent.parent
P3 = P4.parent / "project3-player-churn"
SRC_DB = P3 / "data" / "processed" / "churn.duckdb"
DATA_JS = P3 / "dashboard" / "data.js"
OUT_DB = P4 / "data" / "churn_agent.duckdb"

TABLES = ["features", "labeled", "club_mapping"]

if not SRC_DB.exists():
    sys.exit(f"Project 3 database not found at {SRC_DB}.\n"
             "Run Project 3's pipeline first: cd ../project3-player-churn && "
             ".venv/bin/python src/run_pipeline.py")

OUT_DB.unlink(missing_ok=True)
con = duckdb.connect(str(OUT_DB))
con.execute(f"ATTACH '{SRC_DB}' AS p3 (READ_ONLY)")
for t in TABLES:
    con.execute(f"CREATE TABLE {t} AS SELECT * FROM p3.{t}")
    print(f"copied {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,} rows")

payload = json.loads(re.sub(r"^const DATA = |;$", "", DATA_JS.read_text(encoding="utf-8").strip()))
rows = payload["players"]  # [name, club, age, position_group, overall, wage_eur, risk, churned]
con.execute("CREATE TABLE model_scores (name VARCHAR, club VARCHAR, age BIGINT, overall BIGINT, churn_risk DOUBLE)")
con.executemany("INSERT INTO model_scores VALUES (?,?,?,?,?)",
                [(r[0], r[1], r[2], r[4], r[6]) for r in rows])
# Drop composite-key collisions instead of guessing which score belongs to whom
dupes = con.execute("""
    DELETE FROM model_scores WHERE (name, club, age, overall) IN (
        SELECT (name, club, age, overall) FROM model_scores
        GROUP BY name, club, age, overall HAVING COUNT(*) > 1)
""").fetchone()
print(f"model_scores: {con.execute('SELECT COUNT(*) FROM model_scores').fetchone()[0]:,} rows "
      "(composite-key collisions removed)")

# One convenience view so the LLM doesn't have to re-derive the join every time
con.execute("""
    CREATE VIEW players_scored AS
    SELECT f.*, m.churn_risk
    FROM features f
    LEFT JOIN model_scores m
      ON f.name = m.name AND f.club = m.club AND f.age = m.age AND f.overall = m.overall
""")
matched = con.execute("SELECT COUNT(churn_risk) FROM players_scored").fetchone()[0]
print(f"players_scored view: {matched:,} of "
      f"{con.execute('SELECT COUNT(*) FROM players_scored').fetchone()[0]:,} rows have a risk score")
con.close()
print(f"\nSnapshot written: {OUT_DB} ({OUT_DB.stat().st_size // 1024} KB)")
