from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_DB_PATH = "~/.fpl/league_history.sqlite"


def _get_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_history (
            league_id INTEGER NOT NULL,
            league_name TEXT,
            gameweek INTEGER NOT NULL,
            entry_id INTEGER NOT NULL,
            entry_name TEXT,
            position INTEGER,
            total INTEGER,
            points_for INTEGER,
            points_against INTEGER,
            PRIMARY KEY (league_id, gameweek, entry_id)
        )
        """
    )
    conn.commit()


def save_league_history(df: pd.DataFrame, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Persist normalized league standings rows at the current gameweek snapshot."""
    if df.empty:
        return

    required = [
        "league_id",
        "league_name",
        "gameweek",
        "entry_id",
        "entry_name",
        "position",
        "total",
        "points_for",
        "points_against",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for league history: {missing}")

    conn = _get_connection(db_path)
    try:
        _ensure_schema(conn)
        payload = df[required].copy()
        payload = payload.where(pd.notna(payload), None)
        payload.to_sql(
            "league_history",
            conn,
            if_exists="append",
            index=False,
        )
        conn.commit()
    finally:
        conn.close()


def load_league_history(league_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Load the stored history for a league into a tidy DataFrame."""
    conn = _get_connection(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM league_history
            WHERE league_id = ?
            ORDER BY gameweek ASC, position ASC
            """,
            conn,
            params=(league_id,),
        )
    finally:
        conn.close()

    return df
