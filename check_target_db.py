from sqlalchemy import create_engine, text

url = "postgresql://skyguard_postgres_3kgr_user:bLSvptKXNS3QBZNIoMeAqOsL1usRYWFT@dpg-d7t72cog4nts73epngg0-a.oregon-postgres.render.com/skyguard_postgres_3kgr"
engine = create_engine(url)
tables = ['users','user_preferences','watchlists','alerts','analytics_history','audit_logs','system_metrics','email_otps']
with engine.connect() as conn:
    print('Connected to target DB')
    for t in tables:
        try:
            c = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        except Exception as e:
            c = f'ERROR: {e}'
        print(f"{t}: {c}")
    # orphan alerts
    try:
        orphan = conn.execute(text("SELECT count(*) FROM alerts a LEFT JOIN watchlists w ON a.watchlist_id = w.id WHERE w.id IS NULL")).scalar()
    except Exception as e:
        orphan = f'ERROR: {e}'
    print('orphan_alerts:', orphan)
    # distinct id vs total rows
    for t in tables:
        try:
            r = conn.execute(text(f"SELECT count(DISTINCT id), count(*) FROM {t}")).fetchone()
            print(f"{t} distinct_ids={r[0]} total_rows={r[1]}")
        except Exception as e:
            print(f"{t} distinct/total ERROR: {e}")
