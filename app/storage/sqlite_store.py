import sqlite3
from pathlib import Path
from typing import Any


class SqliteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, params)
            connection.commit()

    def executemany(self, sql: str, seq_of_params: list[tuple[Any, ...]]) -> None:
        with self.connect() as connection:
            connection.executemany(sql, seq_of_params)
            connection.commit()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            cursor = connection.execute(sql, params)
            return cursor.fetchall()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as connection:
            cursor = connection.execute(sql, params)
            return cursor.fetchone()

    def count(self, table_name: str) -> int:
        row = self.fetchone(f"SELECT COUNT(*) AS cnt FROM {table_name}")
        if row is None:
            raise RuntimeError(f"Unable to count table: {table_name}")
        return int(row["cnt"])
