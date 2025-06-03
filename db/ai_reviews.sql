CREATE TABLE IF NOT EXISTS ai_reviews (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    mr_iid INTEGER NOT NULL,
    passed BOOLEAN,
    comment_count INTEGER,
    feedback_rating INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)