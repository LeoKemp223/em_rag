"""存储层：ChromaDB 向量存储 + SQLite FTS5 全文索引"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import pysqlite3 as sqlite3
    sys.modules["sqlite3"] = sqlite3
except ImportError:
    import sqlite3

from src.chunker import Chunk
from src.config import StorageConfig


class VectorStore:
    """ChromaDB 向量存储"""

    def __init__(self, config: StorageConfig):
        import chromadb

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
            documents.append(chunk.retrieval_text)
            metadatas.append({
                "doc_id": doc_id,
                "display_content": chunk.content,
                "context_chain": chunk.context_chain,
                "element_type": chunk.element_type,
                "page": chunk.page,
                "keywords": json.dumps(chunk.keywords),
                "related_images": json.dumps(chunk.metadata.get("related_images", [])),
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
                    "content": results["metadatas"][0][i].get(
                        "display_content", results["documents"][0][i]
                    ),
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
                retrieval_text TEXT,
                context_chain TEXT,
                element_type TEXT,
                page INTEGER,
                keywords TEXT,
                related_images TEXT DEFAULT '[]'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content, keywords, context_chain,
                content='chunks',
                content_rowid='rowid'
            );
            DROP TRIGGER IF EXISTS chunks_ai;
            DROP TRIGGER IF EXISTS chunks_ad;
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, content, keywords, context_chain)
                VALUES (
                    new.rowid,
                    COALESCE(new.retrieval_text, new.content),
                    new.keywords,
                    new.context_chain
                );
            END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, keywords, context_chain)
                VALUES (
                    'delete',
                    old.rowid,
                    COALESCE(old.retrieval_text, old.content),
                    old.keywords,
                    old.context_chain
                );
            END;
        """)
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(chunks)")
        }
        if "related_images" not in columns:
            self.conn.execute("ALTER TABLE chunks ADD COLUMN related_images TEXT DEFAULT '[]'")
        if "retrieval_text" not in columns:
            self.conn.execute("ALTER TABLE chunks ADD COLUMN retrieval_text TEXT")
        self.conn.commit()

    def add_chunks(self, chunks: list[Chunk], doc_id: str):
        rows = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{doc_id}_{i}".encode()).hexdigest()
            rows.append((
                chunk_id,
                doc_id,
                chunk.content,
                chunk.retrieval_text,
                chunk.context_chain,
                chunk.element_type,
                chunk.page,
                " ".join(chunk.keywords),
                json.dumps(chunk.metadata.get("related_images", [])),
            ))

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (
                chunk_id, doc_id, content, retrieval_text, context_chain,
                element_type, page, keywords, related_images
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def search(
        self, keywords: list[str], top_k: int = 5, doc_filter: str = None
    ) -> list[dict]:
        if not keywords:
            return []

        keywords = self._expand_keywords(keywords)
        query = " OR ".join(f'"{kw}"' for kw in keywords)
        filter_sql = "AND c.doc_id = ?" if doc_filter else ""
        sql = """
            SELECT c.chunk_id, c.content, c.context_chain, c.element_type,
                   c.page, c.doc_id, c.related_images, c.retrieval_text, rank
            FROM chunks_fts f
            JOIN chunks c ON c.rowid = f.rowid
            WHERE chunks_fts MATCH ?
            {filter_sql}
            ORDER BY rank
            LIMIT ?
        """.format(filter_sql=filter_sql)
        params = [query]
        if doc_filter:
            params.append(doc_filter)
        params.append(top_k * 4)
        cursor = self.conn.execute(sql, params)
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
                    "related_images": row[6] or "[]",
                },
                "distance": 0.0,
                "rank": row[8],
                "retrieval_text": row[7] or row[1],
            })
        return self._rerank_fts_results(results, keywords)[:top_k]

    def _rerank_fts_results(
        self, results: list[dict], keywords: list[str]
    ) -> list[dict]:
        timing_query = self._is_timing_query(keywords)
        scored = []
        for index, result in enumerate(results):
            meta = result.get("metadata", {})
            text = " ".join([
                result.get("retrieval_text") or "",
                result.get("content") or "",
                meta.get("context_chain", ""),
            ])
            score = 0.0
            score += self._keyword_hit_count(text, keywords) * 8
            if meta.get("element_type") == "figure":
                score += 30 if timing_query else 10
            if meta.get("related_images") not in ("", "[]", None):
                score += 5
            score += max(0, 20 - int(meta.get("page", 0) or 0)) * 0.05
            score -= index * 0.01
            scored.append((score, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [result for _, result in scored]

    def _keyword_hit_count(self, text: str, keywords: list[str]) -> int:
        count = 0
        for keyword in keywords:
            if self._contains_keyword(text, keyword):
                count += 1
        return count

    def _is_timing_query(self, keywords: list[str]) -> bool:
        timing_terms = {
            "TIMING", "WAVEFORM", "SCL", "SDA", "ACK", "NACK",
            "START", "STOP", "TSU", "THD", "TWR", "TLOW", "THIGH",
            "TAA", "TDH", "TDAT", "CLOCK", "时序", "波形",
            "应答", "非应答", "应答查询", "起始", "停止",
            "字节写", "页写", "写周期", "随机读", "顺序读",
            "当前地址读", "建立时间", "保持时间",
        }
        return any(keyword.upper() in timing_terms for keyword in keywords)

    def _expand_keywords(self, keywords: list[str]) -> list[str]:
        alias_map = {
            "时序": ["timing"],
            "波形": ["waveform"],
            "应答": ["ACK", "acknowledge"],
            "非应答": ["NACK", "no acknowledge"],
            "应答查询": ["ACK", "ACK polling"],
            "起始": ["START", "START condition"],
            "停止": ["STOP", "STOP condition"],
            "字节写": ["byte write"],
            "页写": ["page write"],
            "写周期": ["write cycle", "tWR"],
            "当前地址读": ["current address read"],
            "随机读": ["random read"],
            "顺序读": ["sequential read"],
            "建立时间": ["setup time", "tSU"],
            "保持时间": ["hold time", "tHD"],
        }
        expanded = []
        for keyword in keywords:
            expanded.append(keyword)
            expanded.extend(alias_map.get(keyword, []))
        return list(dict.fromkeys(expanded))

    def _contains_keyword(self, text: str, keyword: str) -> bool:
        if not keyword:
            return False
        if re.search(r"[\u4e00-\u9fff]", keyword):
            return keyword in text
        return bool(re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE))

    def fetch_context(
        self,
        doc_id: str,
        page: int,
        context_chain: str = "",
        radius: int = 1,
        limit: int = 6,
    ) -> list[dict]:
        """Fetch nearby page/section chunks for retrieval expansion."""
        clauses = ["doc_id = ?"]
        params: list = [doc_id]

        page_min = max(page - radius, 0)
        page_max = page + radius
        page_clause = "(page BETWEEN ? AND ?)"
        params.extend([page_min, page_max])

        if context_chain:
            section_clause = "context_chain = ?"
            clauses.append(f"({page_clause} OR {section_clause})")
            params.append(context_chain)
        else:
            clauses.append(page_clause)

        sql = f"""
            SELECT chunk_id, content, context_chain, element_type,
                   page, doc_id, related_images
            FROM chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY ABS(page - ?), element_type = 'figure' DESC, page, rowid
            LIMIT ?
        """
        params.extend([page, limit])
        cursor = self.conn.execute(sql, params)
        return [
            {
                "chunk_id": row[0],
                "content": row[1],
                "metadata": {
                    "context_chain": row[2],
                    "element_type": row[3],
                    "page": row[4],
                    "doc_id": row[5],
                    "related_images": row[6] or "[]",
                },
                "distance": 0.0,
            }
            for row in cursor
        ]

    def remove_doc(self, doc_id: str):
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
