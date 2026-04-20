from __future__ import annotations

import argparse
import os
from pathlib import Path

from psycopg import connect


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SQL_PATH = ROOT_DIR / "sql" / "001_research_schema.sql"
DEFAULT_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/second_brain"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize the Second Brain research schema in PostgreSQL."
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("POSTGRES_DSN", DEFAULT_DSN),
        help="PostgreSQL DSN. Defaults to POSTGRES_DSN or the local development DSN.",
    )
    parser.add_argument(
        "--sql-file",
        default=str(DEFAULT_SQL_PATH),
        help="Path to the SQL schema file to execute.",
    )
    return parser.parse_args()


def run_schema(dsn: str, sql_file: Path) -> None:
    if not sql_file.exists():
        raise SystemExit(f"Schema file not found: {sql_file}")

    sql = sql_file.read_text(encoding="utf-8").strip()
    if not sql:
        raise SystemExit(f"Schema file is empty: {sql_file}")

    print(f"Connecting to PostgreSQL: {dsn}")
    print(f"Executing schema file: {sql_file}")

    with connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)

    print("Research schema initialized successfully.")


def main() -> None:
    args = parse_args()
    run_schema(args.dsn, Path(args.sql_file).resolve())


if __name__ == "__main__":
    main()
