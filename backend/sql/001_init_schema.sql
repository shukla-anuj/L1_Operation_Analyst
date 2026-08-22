-- 001_init_schema.sql
-- Create base tables for incidents, embeddings, and architecture docs

CREATE TABLE IF NOT EXISTS incidents (
    incident_id SERIAL PRIMARY KEY,
    service VARCHAR(50),
    error_log TEXT,
    root_cause TEXT,
    resolution TEXT,
    validated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS incident_embeddings (
    incident_id INT REFERENCES incidents(incident_id),
    embedding vector(1536)  -- adjust to match your embedding model dimension
);

CREATE TABLE IF NOT EXISTS architecture_docs (
    doc_id SERIAL PRIMARY KEY,
    title VARCHAR(100),
    content TEXT,
    image_path TEXT,   -- reference to image file or URL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
