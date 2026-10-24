#!/usr/bin/env python3
"""
AgentOps MCP — Database Backup and Restore Utility.

Supports both SQLite (via atomic online backup API) and PostgreSQL (via pg_dump).
Ensures safe snapshot creation without credentials leakage.

Usage:
    python scripts/backup_db.py backup [--output-dir DIR]
    python scripts/backup_db.py restore --input-file FILE [--force]
    python scripts/backup_db.py verify --input-file FILE
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def _get_database_url() -> str:
    url = os.environ.get("MARG_DATABASE_URL") or os.environ.get("AGENTOPS_DATABASE_URL")
    if url:
        return url
    pg_host = os.environ.get("POSTGRES_HOST")
    if pg_host:
        user = os.environ.get("POSTGRES_USER", "marg")
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        db = os.environ.get("POSTGRES_DB", "marg")
        port = os.environ.get("POSTGRES_PORT", "5432")
        return f"postgresql://{user}:{pw}@{pg_host}:{port}/{db}"
    # Default fallback
    return "sqlite:///marg.db"


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:") or url.endswith(".db") or url.endswith(".sqlite")


def _sqlite_path_from_url(url: str) -> Path:
    if url.startswith("sqlite:///"):
        path_str = url.replace("sqlite:///", "")
        return Path(path_str).resolve()
    if url.startswith("sqlite://"):
        path_str = url.replace("sqlite://", "")
        return Path(path_str).resolve()
    return Path(url).resolve()


def backup_sqlite(db_path: Path, output_dir: Path) -> Path:
    """Create an atomic, non-blocking online backup of an SQLite database."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_file = output_dir / f"agentops_backup_{timestamp}.db"

    # Use SQLite Online Backup API for safe snapshot during concurrent writes
    source_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dest_conn = sqlite3.connect(target_file)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    size_bytes = target_file.stat().st_size
    print(f"[SUCCESS] SQLite backup created: {target_file} ({size_bytes:,} bytes)")
    return target_file


def backup_postgres(url: str, output_dir: Path) -> Path:
    """Dump PostgreSQL database using pg_dump without exposing credentials in logs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_file = output_dir / f"agentops_pg_backup_{timestamp}.dump"

    # Check for pg_dump
    pg_dump_bin = shutil.which("pg_dump")
    if not pg_dump_bin:
        raise RuntimeError(
            "pg_dump executable not found in PATH. Install postgresql-client or run inside container."
        )

    parsed = urlparse(url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    cmd = [
        pg_dump_bin,
        "-h", parsed.hostname or "localhost",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-F", "c",  # Custom compressed format
        "-b",       # Include blobs
        "-v",
        "-f", str(target_file),
        parsed.path.lstrip("/"),
    ]

    # Run pg_dump without printing password
    print(f"Executing pg_dump for {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}...")
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit {res.returncode}): {res.stderr}")

    size_bytes = target_file.stat().st_size
    print(f"[SUCCESS] PostgreSQL backup created: {target_file} ({size_bytes:,} bytes)")
    return target_file


def verify_backup(backup_file: Path) -> bool:
    """Verify backup integrity."""
    if not backup_file.exists():
        print(f"[ERROR] Backup file does not exist: {backup_file}")
        return False

    size = backup_file.stat().st_size
    if size == 0:
        print(f"[ERROR] Backup file is empty: {backup_file}")
        return False

    # Check if SQLite
    if backup_file.suffix == ".db":
        try:
            conn = sqlite3.connect(backup_file)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] == "ok":
                print(f"[VERIFIED] SQLite backup is valid and intact ({size:,} bytes).")
                return True
            print(f"[ERROR] SQLite integrity check failed: {row}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to verify SQLite backup: {e}")
            return False

    # For postgres custom dump
    print(f"[VERIFIED] Backup file exists and is non-empty ({size:,} bytes).")
    return True


def restore_sqlite(backup_file: Path, target_db: Path, force: bool = False) -> None:
    """Restore an SQLite database from backup."""
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    if not verify_backup(backup_file):
        raise ValueError("Backup file verification failed. Restore aborted.")

    if target_db.exists() and not force:
        raise RuntimeError(
            f"Target database already exists at {target_db}. Pass --force to overwrite."
        )

    # Make safety copy of current DB if exists
    if target_db.exists():
        safety_copy = target_db.with_suffix(f".pre_restore_{int(time.time())}.bak")
        shutil.copy2(target_db, safety_copy)
        print(f"[NOTICE] Pre-restore copy preserved at {safety_copy}")

    shutil.copy2(backup_file, target_db)
    print(f"[SUCCESS] Database restored successfully to {target_db}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOps MCP Database Backup & Restore Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create a database backup")
    backup_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backups"),
        help="Directory where backup will be stored (default: ./backups)",
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify integrity of a backup file")
    verify_parser.add_argument("--input-file", type=Path, required=True, help="Backup file to verify")

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore database from backup")
    restore_parser.add_argument("--input-file", type=Path, required=True, help="Backup file to restore from")
    restore_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing database",
    )

    args = parser.parse_args()
    db_url = _get_database_url()

    try:
        if args.command == "backup":
            if _is_sqlite(db_url):
                sqlite_path = _sqlite_path_from_url(db_url)
                backup_file = backup_sqlite(sqlite_path, args.output_dir)
                verify_backup(backup_file)
            else:
                backup_file = backup_postgres(db_url, args.output_dir)
                verify_backup(backup_file)

        elif args.command == "verify":
            valid = verify_backup(args.input_file)
            return 0 if valid else 1

        elif args.command == "restore":
            if _is_sqlite(db_url):
                sqlite_path = _sqlite_path_from_url(db_url)
                restore_sqlite(args.input_file, sqlite_path, force=args.force)
            else:
                print(
                    "[INFO] For PostgreSQL, execute:\n"
                    f"  pg_restore -h <host> -U <user> -d <dbname> -c -v {args.input_file}"
                )

        return 0
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
