"""Copy data from the local SQLite database into a Postgres database.

Use this once after creating a Render Postgres database and before switching
the deployed service to the new DATABASE_URL.
"""

import argparse
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
import math

from src.database.models import (
    Alert,
    AnalyticsHistory,
    AuditLog,
    Base,
    EmailOTP,
    SystemMetrics,
    User,
    UserPreferences,
    Watchlist,
)


TABLE_ORDER = [
    User,
    UserPreferences,
    Watchlist,
    Alert,
    AnalyticsHistory,
    AuditLog,
    SystemMetrics,
    EmailOTP,
]


def make_engine(database_url):
    kwargs = {'echo': False, 'pool_pre_ping': True}
    if database_url.startswith('sqlite:'):
        kwargs['connect_args'] = {'check_same_thread': False}
    return create_engine(database_url, **kwargs)


@contextmanager
def session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def copy_rows(source_session, target_session, model):
    rows = source_session.query(model).all()
    if not rows:
        print(f"  - {model.__tablename__}: no rows")
        return 0

    # Prepare list of dicts for insertion
    dict_rows = [
        {column.name: getattr(row, column.name) for column in model.__table__.columns}
        for row in rows
    ]

    copied = 0
    dialect = target_session.bind.dialect.name

    # Use chunked inserts to avoid long transactions and per-row roundtrips
    chunk_size = 500
    for i in range(0, len(dict_rows), chunk_size):
        chunk = dict_rows[i:i+chunk_size]
        if dialect == 'postgresql':
            stmt = pg_insert(model.__table__).values(chunk)
            # ON CONFLICT DO NOTHING to be idempotent
            stmt = stmt.on_conflict_do_nothing(index_elements=[model.__table__.primary_key.columns.keys()[0]])
            target_session.execute(stmt)
        else:
            # Fallback: use merge per row for SQLite or unknown dialects
            for data in chunk:
                target_session.merge(model(**data))
        target_session.commit()
        copied += len(chunk)

    print(f"  - {model.__tablename__}: {copied} rows")
    return copied


def migrate(source_url, target_url):
    source_engine = make_engine(source_url)
    target_engine = make_engine(target_url)

    Base.metadata.create_all(bind=target_engine)

    SourceSession = sessionmaker(bind=source_engine, autoflush=False, autocommit=False)
    TargetSession = sessionmaker(bind=target_engine, autoflush=False, autocommit=False)

    total = 0
    # Copy table-by-table, committing after each table to satisfy FK order
    source_session = SourceSession()
    try:
        for model in TABLE_ORDER:
            target_session = TargetSession()
            try:
                total += copy_rows(source_session, target_session, model)
            finally:
                target_session.close()
    finally:
        source_session.close()

        # Backward-compatible migration for older SQLite databases that used
        # the singular email_otp table name.
        if source_engine.dialect.name == 'sqlite':
            existing = source_session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='email_otp'")
            ).fetchone()
            if existing:
                legacy_rows = source_session.execute(text("SELECT * FROM email_otp")).mappings().all()
                if legacy_rows:
                    for row in legacy_rows:
                        payload = {
                            'id': row.get('id'),
                            'email': row.get('email'),
                            'otp_code': row.get('otp_code'),
                            'purpose': row.get('purpose', 'signup'),
                            'is_verified': bool(row.get('is_verified', 0)),
                            'attempts': row.get('attempt_count', row.get('attempts', 0)),
                            'max_attempts': row.get('max_attempts', 5),
                            'created_at': row.get('created_at'),
                            'expires_at': row.get('expires_at'),
                            'verified_at': row.get('verified_at'),
                        }
                        target_session.merge(EmailOTP(**payload))
                        total += 1
                    print(f"  - email_otp (legacy): {len(legacy_rows)} rows")

    print(f"\nMigration complete. Copied {total} rows.")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='Copy SQLite data into Postgres.')
    parser.add_argument('--source', default='sqlite:///flight_risk_ai.db', help='Source SQLite URL')
    parser.add_argument('--target', default=os.environ.get('DATABASE_URL'), help='Target database URL')
    args = parser.parse_args()

    if not args.target:
        raise SystemExit('Target DATABASE_URL is required. Set it or pass --target.')

    print('Starting migration...')
    print(f'Source: {args.source}')
    print(f'Target: {args.target}')
    migrate(args.source, args.target)


if __name__ == '__main__':
    main()