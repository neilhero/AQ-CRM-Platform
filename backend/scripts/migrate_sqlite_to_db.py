"""Migrate the local SQLite database into DATABASE_URL.

Usage:
  set DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/aq_crm
  python backend/scripts/migrate_sqlite_to_db.py

The target database is created from SQLAlchemy models and then loaded table by
table. Existing target rows are left in place unless --truncate is provided.
"""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.database import DEFAULT_SQLITE_PATH
from app.models import Base
from app.models import (
    User, Customer, ChannelPartner, Contact, Product, Opportunity, FollowUp,
    CommissionRule, Lead, MenuConfig, StageConfig, IndustryConfig, AuditLog,
)

MODELS = [
    User, Customer, ChannelPartner, Contact, Product, Opportunity, FollowUp,
    CommissionRule, Lead, MenuConfig, StageConfig, IndustryConfig, AuditLog,
]


def _engine(url: str):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


def _row_dict(obj):
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


def _reset_identity(session, engine, model):
    pk_cols = list(model.__table__.primary_key.columns)
    if len(pk_cols) != 1:
        return
    pk = pk_cols[0]
    if not getattr(pk, "autoincrement", False):
        return
    table = model.__tablename__
    column = pk.name
    dialect = engine.dialect.name
    if dialect == "postgresql":
        session.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
            f"COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1, false)"
        ))
    elif dialect in ("mysql", "mariadb"):
        max_id = session.execute(text(f"SELECT COALESCE(MAX({column}), 0) + 1 FROM {table}")).scalar()
        session.execute(text(f"ALTER TABLE {table} AUTO_INCREMENT = {int(max_id or 1)}"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=f"sqlite:///{DEFAULT_SQLITE_PATH}", help="SQLite source URL")
    parser.add_argument("--target", default=os.getenv("DATABASE_URL"), help="Target PostgreSQL/MySQL DATABASE_URL")
    parser.add_argument("--truncate", action="store_true", help="Delete target data before import")
    args = parser.parse_args()
    if not args.target:
        raise SystemExit("Missing target DATABASE_URL. Pass --target or set DATABASE_URL.")
    if args.target.startswith("sqlite"):
        raise SystemExit("Target must be PostgreSQL/MySQL, not SQLite.")

    source_engine = _engine(args.source)
    target_engine = _engine(args.target)
    Base.metadata.create_all(bind=target_engine)

    Source = sessionmaker(bind=source_engine)
    Target = sessionmaker(bind=target_engine)
    src = Source()
    dst = Target()
    try:
        if args.truncate:
            for model in reversed(MODELS):
                dst.execute(delete(model))
            dst.commit()

        for model in MODELS:
            rows = src.query(model).order_by(*model.__table__.primary_key.columns).all()
            if not rows:
                continue
            dst.bulk_insert_mappings(model, [_row_dict(row) for row in rows])
            dst.commit()
            _reset_identity(dst, target_engine, model)
            dst.commit()
            print(f"{model.__tablename__}: {len(rows)}")
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
