"""Fix stale DB state: recreate resource_locks table without unique constraint, clean queue entries."""
import sqlite3

conn = sqlite3.connect('c:/DistributedVerificationFramework/data/app.db')
c = conn.cursor()

# Drop and recreate resource_locks without unique constraints on resource_id/run_id
c.execute("DROP TABLE IF EXISTS resource_locks")
c.execute("""
CREATE TABLE resource_locks (
    id INTEGER NOT NULL PRIMARY KEY,
    resource_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    acquired_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    released_at DATETIME,
    FOREIGN KEY(resource_id) REFERENCES resources(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
)
""")
c.execute("CREATE INDEX ix_resource_locks_resource_id ON resource_locks(resource_id)")
c.execute("CREATE INDEX ix_resource_locks_run_id ON resource_locks(run_id)")

# Delete all stale queue entries
c.execute("DELETE FROM queue_entries")

print("Done. resource_locks recreated, queue_entries cleared.")
print(f"  Deleted queue entries: {c.rowcount}")

conn.commit()
conn.close()
