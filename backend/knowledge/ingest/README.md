# Knowledge Ingest

Ingestion converts uploaded files into normalized knowledge records.

Pipeline:

1. Parse source file.
2. Classify knowledge type.
3. Split into chunks.
4. Extract metadata.
5. Create embeddings.
6. Store source text and vector data.
7. Return warnings and document IDs.

This directory starts as a framework placeholder; implementation can be added incrementally.

