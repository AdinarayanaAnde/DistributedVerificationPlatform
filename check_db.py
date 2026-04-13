import sqlite3
conn = sqlite3.connect('c:/DistributedVerificationFramework/data/app.db')
c = conn.cursor()

print("=== Tables ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
for r in c.fetchall():
    print(r)

print("\n=== Runs (last 10) ===")
c.execute("SELECT id, status, created_at FROM runs ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    print(r)

print("\n=== Resource Locks ===")
c.execute("SELECT * FROM resource_locks")
for r in c.fetchall():
    print(r)

print("\n=== Queue Entries ===")
c.execute("SELECT * FROM queue_entries")
for r in c.fetchall():
    print(r)

print("\n=== Resources ===")
c.execute("SELECT * FROM resources")
for r in c.fetchall():
    print(r)

print("\n=== Log Entries (last 10) ===")
c.execute("SELECT id, run_id, stream, substr(line,1,80) FROM log_entries ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    print(r)

conn.close()
