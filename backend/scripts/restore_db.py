"""Restore a database backup.

Stop the application before running this in production.
SQLite restores by replacing the db file after creating a safety copy.
PostgreSQL/MySQL restore from SQL dump through psql/mysql.
"""

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "aq_crm.db"


def restore_sqlite(database_url: str, backup_file: Path):
    db_path = Path(database_url.replace("sqlite:///", ""))
    if db_path.exists():
        safety = db_path.with_suffix(f".before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db")
        shutil.copy2(db_path, safety)
        print(f"safety_backup={safety}")
    shutil.copy2(backup_file, db_path)
    wal = db_path.with_suffix(db_path.suffix + "-wal")
    shm = db_path.with_suffix(db_path.suffix + "-shm")
    for extra in (wal, shm):
        if extra.exists():
            extra.unlink()


def restore_dump(database_url: str, backup_file: Path):
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split("+")[0]
    if scheme in ("postgresql", "postgres"):
        subprocess.run(["psql", database_url, "-f", str(backup_file)], check=True)
    elif scheme in ("mysql", "mariadb"):
        db_name = parsed.path.lstrip("/")
        host = parsed.hostname or "127.0.0.1"
        port = str(parsed.port or 3306)
        user = parsed.username or ""
        env = os.environ.copy()
        if parsed.password:
            env["MYSQL_PWD"] = parsed.password
        with backup_file.open("rb") as fh:
            subprocess.run(["mysql", "-h", host, "-P", port, "-u", user, db_name], check=True, env=env, stdin=fh)
    else:
        raise SystemExit(f"Unsupported database scheme: {parsed.scheme}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_file")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}"))
    args = parser.parse_args()
    backup_file = Path(args.backup_file)
    if not backup_file.exists():
        raise SystemExit(f"Backup not found: {backup_file}")
    if args.database_url.startswith("sqlite"):
        restore_sqlite(args.database_url, backup_file)
    elif args.database_url.startswith(("postgres", "mysql", "mariadb")):
        restore_dump(args.database_url, backup_file)
    else:
        raise SystemExit("Unsupported DATABASE_URL")
    print("restore complete")


if __name__ == "__main__":
    main()
