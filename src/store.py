"""存储层：ChromaDB 向量存储 + SQLite FTS5 全文索引"""

import hashlib
import json
import sqlite3
from pathlib import Path

import chromadb

from src.chunker import Chunk
from src.config import StorageConfig


class VectorStore:
    """ChromaDB 向量存储"""

    def __init__(self, config: StorageConfig):
        persist_dir = Path(config.chroma_path)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(
            name="em_rag",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]], doc_id: str):
        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = self._make_id(doc_id, i)
            ids.append(chunk_id)
            documents.append(chunk.content)
            metadatas.append({
                "doc_id": doc_id,
                "context_chain": chunk.context_chain,
                "element_type": chunk.element_type,
                "page": chunk.page,
                "keywords": json.dumps(chunk.keywords),
            })

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self, query_embedding: list[float], top_k: int = 5, doc_filter: str = None
    ) -> list[dict]:
        where = {"doc_id": doc_filter} if doc_filter else None
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                items.append({
                    "chunk_id": chunk_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
        return items

    def remove_doc(self, doc_id: str):
        results = self.collection.get(where={"doc_id": doc_id})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])

    def list_docs(self) -> list[str]:
        results = self.collection.get(include=["metadatas"])
        doc_ids = set()
        if results["metadatas"]:
            for meta in results["metadatas"]:
                if meta and "doc_id" in meta:
                    doc_ids.add(meta["doc_id"])
        return sorted(doc_ids)

    def _make_id(self, doc_id: str, index: int) -> str:
        raw = f"{doc_id}_{index}"
        return hashlib.md5(raw.encode()).hexdigest()


class FTSStore:
    """SQLite FTS5 全文索引"""

    def __init__(self, config: StorageConfig):
        db_path = Path(config.fts_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT,
                content TEXT,
                context_chain TEXT,
                element_type TEXT,
                page INTEGER,
                keywords TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content, keywords, context_chain,
                content='chunks',
                content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, content, keywords, context_chain)
                VALUES (new.rowid, new.content, new.keywords, new.context_chain);
            END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, keywords, context_chain)
                VALUES ('delete', old.rowid, old.content, old.keywords, old.context_chain);
            END;
        """)
        self.conn.commit()

    def add_chunks(self, chunks: list[Chunk], doc_id: str):
        rows = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{doc_id}_{i}".encode()).hexdigest()
            rows.append((
                chunk_id,
                doc_id,
                chunk.content,
                chunk.context_chain,
                chunk.element_type,
                chunk.page,
                " ".join(chunk.keywords),
            ))

        self.conn.executemany(
            "INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def search(self, keywords: list[str], top_k: int = 5) -> list[dict]:
        if not keywords:
            return []

        query = " OR ".join(f'"{kw}"' for kw in keywords)
        sql = """
            SELECT c.chunk_id, c.content, c.context_chain, c.element_type, c.page, c.doc_id
            FROM chunks_fts f
            JOIN chunks c ON c.rowid = f.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        cursor = self.conn.execute(sql, (query, top_k))
        results = []
        for row in cursor:
            results.append({
                "chunk_id": row[0],
                "content": row[1],
                "metadata": {
                    "context_chain": row[2],
                    "element_type": row[3],
                    "page": row[4],
                    "doc_id": row[5],
                },
                "distance": 0.0,
            })
        return results

    def remove_doc(self, doc_id: str):
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
