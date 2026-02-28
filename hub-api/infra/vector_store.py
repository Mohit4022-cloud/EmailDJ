"""
Vector Store — abstraction over Pinecone or pgvector.

IMPLEMENTATION INSTRUCTIONS:
Exports:
  upsert(account_id: str, embedding: list[float], metadata: dict) → None
  query(embedding: list[float], top_k: int) → list[Match]
  delete(account_id: str) → None

Backend selection: read VECTOR_STORE_BACKEND env var.
  - "pinecone" (default): Pinecone serverless index
  - "pgvector": PostgreSQL with pgvector extension

Match (dataclass):
  { account_id: str, score: float, metadata: dict }

Pinecone backend:
  1. Initialize Pinecone client:
     from pinecone import Pinecone
     pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
     index = pc.Index(os.environ["PINECONE_INDEX_NAME"])
     Index config: dimension=1536, metric="cosine", serverless spec (us-east-1)
  2. upsert(): index.upsert(vectors=[{"id": account_id, "values": embedding,
     "metadata": metadata}])
  3. query(): results = index.query(vector=embedding, top_k=top_k, include_metadata=True)
     Return [Match(id, score, metadata) for id in results.matches]
  4. delete(): index.delete(ids=[account_id])

pgvector backend:
  1. Use SQLAlchemy with pgvector extension.
  2. Table schema: account_embeddings(id uuid, account_id text unique,
     embedding halfvec(1536), metadata jsonb, created_at timestamp)
     (halfvec = 2-byte float storage, more efficient than vector)
  3. upsert(): INSERT ... ON CONFLICT (account_id) DO UPDATE SET embedding = ...
  4. query(): SELECT account_id, metadata, 1 - (embedding <=> :query_vec) AS score
     FROM account_embeddings ORDER BY embedding <=> :query_vec LIMIT :top_k
  5. Use pgvector index: CREATE INDEX ON account_embeddings USING ivfflat
     (embedding halfvec_cosine_ops) WITH (lists = 100)

The abstraction must support both backends via VECTOR_STORE_BACKEND env var
so the team can switch without code changes.
"""

import os
from dataclasses import dataclass


VECTOR_STORE_BACKEND = os.environ.get("VECTOR_STORE_BACKEND", "pinecone")


@dataclass
class Match:
    account_id: str
    score: float
    metadata: dict


async def upsert(account_id: str, embedding: list, metadata: dict) -> None:
    # TODO: implement per VECTOR_STORE_BACKEND per instructions above
    raise NotImplementedError("vector_store.upsert not yet implemented")


async def query(embedding: list, top_k: int = 10) -> list:
    # TODO: implement per VECTOR_STORE_BACKEND per instructions above
    raise NotImplementedError("vector_store.query not yet implemented")


async def delete(account_id: str) -> None:
    # TODO: implement per VECTOR_STORE_BACKEND per instructions above
    raise NotImplementedError("vector_store.delete not yet implemented")
