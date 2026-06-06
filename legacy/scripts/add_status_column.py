import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'autoreach_saas.db')
print(f"Connecting to database at {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE google_auth_tokens ADD COLUMN status VARCHAR(30) DEFAULT 'active';")
    conn.commit()
    print("Column 'status' added successfully to 'google_auth_tokens' table.")
except sqlite3.OperationalError as e:
    print(f"OperationalError: {e} (Column might already exist)")

conn.close()
