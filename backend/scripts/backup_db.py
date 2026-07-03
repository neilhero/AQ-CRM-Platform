"""Create a timestamped database backup.

SQLite is copied with sqlite backup API. PostgreSQL/MySQL use pg_dump or
mysqldump, so those client binaries must be installed on the server.
"""

import argparse
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "aq_crm.db"
DEFAULT_DIR = ROOT / "backups"


def backup_sqlite(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def run_dump(database_url: str, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split("+")[0]
    if scheme in ("postgresql", "postgres"):
        cmd = ["pg_dump", database_url, "-f", str(target)]
    elif scheme in ("mysql", "mariadb"):
        # mysqldump reads credentials from the URL through MYSQL_PWD only poorly,
        # so prefer mysql_config_editor or a secured --defaults-extra-file in production.
        db_name = parsed.path.lstrip("/")
        host = parsed.hostname or "127.0.0.1"
        port = str(parsed.port or 3306)
        user = parsed.username or ""
        env = os.environ.copy()
        if parsed.password:
            env["MYSQL_PWD"] = parsed.password
        cmd = ["mysqldump", "-h", host, "-P", port, "-u", user, db_name]
        with target.open("wb") as fh:
            subprocess.run(cmd, check=True, env=env, stdout=fh)
        return
    else:
        raise SystemExit(f"Unsupported database scheme: {parsed.scheme}")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}"))
    parser.add_argument("--out-dir", default=str(DEFAULT_DIR))
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir)
    if args.database_url.startswith("sqlite"):
        db_path = Path(args.database_url.replace("sqlite:///", ""))
        target = out_dir / f"aq_crm-sqlite-{stamp}.db"
        backup_sqlite(db_path, target)
    elif args.database_url.startswith(("postgres", "mysql", "mariadb")):
        suffix = ".sql"
        target = out_dir / f"aq_crm-dump-{stamp}{suffix}"
        run_dump(args.database_url, target)
    else:
        raise SystemExit("Unsupported DATABASE_URL")
    print(target)


if __name__ == "__main__":
    main()
