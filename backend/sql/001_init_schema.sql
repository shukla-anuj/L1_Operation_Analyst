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

DROP TABLE IF EXISTS incident_embeddings;
CREATE TABLE IF NOT EXISTS incident_embeddings (
    incident_id INT REFERENCES incidents(incident_id),
    embedding vector(1536)  -- adjust to match your embedding model dimension
);
ALTER TABLE incident_embeddings
ADD CONSTRAINT incident_embeddings_unique UNIQUE (incident_id);

CREATE TABLE IF NOT EXISTS architecture_docs (
    doc_id SERIAL PRIMARY KEY,
    title VARCHAR(150),          -- Document title
    content TEXT,                -- Main textual content
    image_paths TEXT[],          -- Array of image references (supports multiple diagrams)
    doc_type VARCHAR(50),        -- e.g. 'manual', 'flow', 'architecture'
    file_path TEXT,              -- Path to the actual .docx or .pdf file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE architecture_doc_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    doc_id INT REFERENCES architecture_docs(doc_id),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding vector(384) NOT NULL
);