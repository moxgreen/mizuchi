#!/usr/bin/env python3
"""Import a MySQL dump file into a SQLite database.

This script is built for phpMyAdmin-style dumps like old_data/backup_10_Gen_2026.sql.
It converts common MySQL-specific syntax to SQLite-compatible SQL on the fly.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path


IGNORED_PREFIXES = (
    "SET ",
    "LOCK TABLES",
    "UNLOCK TABLES",
    "DELIMITER",
    "START TRANSACTION",
    "COMMIT",
    "ROLLBACK",
    "CREATE DATABASE",
    "DROP DATABASE",
)

SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}


def split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL script into statements, respecting quoted strings/identifiers."""
    statements: list[str] = []
    current: list[str] = []

    in_single = False
    in_double = False
    in_backtick = False
    escape = False

    for ch in sql_text:
        current.append(ch)

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if in_single:
            if ch == "'":
                in_single = False
            continue

        if in_double:
            if ch == '"':
                in_double = False
            continue

        if in_backtick:
            if ch == "`":
                in_backtick = False
            continue

        if ch == "'":
            in_single = True
            continue

        if ch == '"':
            in_double = True
            continue

        if ch == "`":
            in_backtick = True
            continue

        if ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []

    leftover = "".join(current).strip()
    if leftover:
        statements.append(leftover)

    return statements


def strip_comment_lines(sql_text: str) -> str:
    """Remove full-line MySQL comments and versioned directives."""
    kept_lines: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        if stripped.startswith("--"):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("/*!") and stripped.endswith("*/;"):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def normalize_types(stmt: str) -> str:
    """Map common MySQL data types/modifiers to SQLite-friendly variants."""
    stmt = re.sub(r"\bunsigned\b", "", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bzerofill\b", "", stmt, flags=re.IGNORECASE)

    stmt = re.sub(r"\benum\s*\((?:[^)(]|\([^)(]*\))*\)", "TEXT", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bset\s*\((?:[^)(]|\([^)(]*\))*\)", "TEXT", stmt, flags=re.IGNORECASE)

    stmt = re.sub(r"\btinyint\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bsmallint\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bmediumint\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bint\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\binteger\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bbigint\s*\(\s*\d+\s*\)", "INTEGER", stmt, flags=re.IGNORECASE)

    stmt = re.sub(r"\bdouble\b", "REAL", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\bfloat\b", "REAL", stmt, flags=re.IGNORECASE)

    return stmt


def convert_create_table(stmt: str) -> str:
    """Convert MySQL CREATE TABLE statement into SQLite-compatible SQL."""
    stmt = stmt.replace("`", '"')
    stmt = normalize_types(stmt)

    stmt = re.sub(r"\bAUTO_INCREMENT\s*=\s*\d+\b", "", stmt, flags=re.IGNORECASE)
    stmt = re.sub(r"\s+AUTO_INCREMENT\b", "", stmt, flags=re.IGNORECASE)

    lines = stmt.splitlines()
    converted_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        unique_match = re.match(r'^UNIQUE\s+KEY\s+"[^"]+"\s*\((.+)\)\s*,?$', stripped, flags=re.IGNORECASE)
        if unique_match:
            suffix = "," if stripped.endswith(",") else ""
            converted_lines.append(f"  UNIQUE ({unique_match.group(1)}){suffix}")
            continue

        plain_key_match = re.match(r'^KEY\s+"[^"]+"\s*\((.+)\)\s*,?$', stripped, flags=re.IGNORECASE)
        if plain_key_match:
            continue

        converted_lines.append(line)

    stmt = "\n".join(converted_lines)

    # Strip MySQL table options appended after the closing parenthesis.
    # Example: ") ENGINE=InnoDB DEFAULT CHARSET=latin1 AUTO_INCREMENT=1234"
    stmt = re.sub(
        r"\)\s*(?:ENGINE|TYPE|DEFAULT|AUTO_INCREMENT|CHARSET|COLLATE)\b.*$",
        ")",
        stmt,
        flags=re.IGNORECASE | re.DOTALL,
    )

    stmt = re.sub(r",\s*\)\s*$", ")", stmt, flags=re.DOTALL)
    return stmt


def convert_statement(stmt: str) -> str | None:
    stripped = stmt.strip().rstrip(";").strip()
    upper = stripped.upper()

    if upper.startswith("/*!"):
        return None

    if upper.startswith(IGNORED_PREFIXES):
        return None

    if upper.startswith("USE "):
        return stripped

    if upper.startswith("CREATE TABLE") or upper.startswith("CREATE TEMPORARY TABLE"):
        return convert_create_table(stripped)

    if upper.startswith("INSERT INTO"):
        return stripped.replace("`", '"')

    if upper.startswith("DROP TABLE"):
        return stripped.replace("`", '"')

    if upper.startswith("ALTER TABLE"):
        return None

    return stripped.replace("`", '"')


def extract_use_database(stmt: str) -> str | None:
    match = re.match(r'^USE\s+[`"]?([^`";\s]+)[`"]?\s*;?$', stmt, flags=re.IGNORECASE)
    return match.group(1) if match else None


def import_dump(
    dump_path: Path,
    sqlite_path: Path,
    include_schemas: set[str] | None,
    exclude_system_schemas: bool,
    encoding: str,
) -> tuple[int, int]:
    raw_text = dump_path.read_text(encoding=encoding)
    text = strip_comment_lines(raw_text)
    statements = split_sql_statements(text)

    executed = 0
    skipped = 0
    active_schema: str | None = None

    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")

        for index, statement in enumerate(statements, start=1):
            use_db = extract_use_database(statement.strip())
            if use_db:
                active_schema = use_db
                skipped += 1
                continue

            converted = convert_statement(statement)
            if not converted:
                skipped += 1
                continue

            if active_schema and include_schemas is not None and active_schema not in include_schemas:
                skipped += 1
                continue

            if active_schema and exclude_system_schemas and active_schema in SYSTEM_SCHEMAS:
                skipped += 1
                continue

            try:
                conn.execute(converted)
            except sqlite3.Error as exc:
                raise sqlite3.OperationalError(
                    f"{exc} (statement #{index}, active schema={active_schema!r}):\n{converted}"
                ) from exc
            executed += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return executed, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a MySQL dump into SQLite")
    parser.add_argument("dump", type=Path, help="Path to .sql dump file")
    parser.add_argument("sqlite", type=Path, help="Path to output SQLite database")
    parser.add_argument(
        "--schema",
        action="append",
        dest="schemas",
        help="Schema/database name to include (repeatable). Defaults to first non-system schema in your dump.",
    )
    parser.add_argument(
        "--include-system-schemas",
        action="store_true",
        help="Also import system schemas (information_schema, mysql, performance_schema, sys).",
    )
    parser.add_argument(
        "--encoding",
        default="latin1",
        help="Input dump encoding (default: latin1).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    include_schemas = set(args.schemas) if args.schemas else {"chiamogna"}

    executed, skipped = import_dump(
        dump_path=args.dump,
        sqlite_path=args.sqlite,
        include_schemas=include_schemas,
        exclude_system_schemas=not args.include_system_schemas,
        encoding=args.encoding,
    )

    print(f"Imported into: {args.sqlite}")
    print(f"Executed statements: {executed}")
    print(f"Skipped statements: {skipped}")
    print(f"Included schemas: {', '.join(sorted(include_schemas))}")


if __name__ == "__main__":
    main()
