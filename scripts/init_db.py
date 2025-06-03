import psycopg2
from config.config import settings

conn = psycopg2.connect(settings.POSTGRES_DSN)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS ai_reviews (
    id SERIAL PRIMARY KEY,
    mr_iid INTEGER,
    project_id INTEGER,
    passed BOOLEAN,
    comment_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
print("Table created or already exists")
