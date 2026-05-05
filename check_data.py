import sqlite3
db='flight_risk_ai.db'
c=sqlite3.connect(db)
print(c.execute("SELECT COUNT(*) FROM system_metrics").fetchone()[0])
