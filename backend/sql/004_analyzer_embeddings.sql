-- Align incident search and ingestion with the 768-dimensional BGE embedding model.
CREATE TABLE IF NOT EXISTS incident_embeddings_768 (
    incident_id INT PRIMARY KEY REFERENCES incidents(incident_id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL
);
