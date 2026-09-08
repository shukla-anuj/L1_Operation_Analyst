# Analyzer Agent

The package exposes `RCAAnalyzerAgent`, a LangGraph workflow with these stages:

1. Extract the failed job name from the incident trace.
2. Search Application Support Manual chunks for the job-to-service mapping.
3. Register the raised incident and store its BGE embedding.
4. Retrieve the top five historical incidents from pgvector.
5. Generate an initial strict JSON RCA with the Hugging Face model.
6. Stop when confidence is at least 95.
7. Otherwise retrieve architecture chunks, derive ranked services, fetch logs, and generate exactly three RCA candidates.
8. Persist the selected RCA and evidence snapshot.

Local development can inject `FlociLogProvider`; AWS deployments can inject `CloudWatchLogProvider`.

Required environment variables:

```env
HF_MODEL_ID=your-instruct-text-generation-model
HUGGINGFACEHUB_API_TOKEN=your-token
```

Example construction:

```python
from src.agents.analyzer_agent import RCAAnalyzerAgent

agent = RCAAnalyzerAgent(db=store, doc_embedder=doc_embedder, log_provider=log_provider)
result = agent.analyze(incident_query=error_text)
```
