import hashlib
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from django.db.models import Q
from openai import OpenAI
from pypdf import PdfReader

from core.models import CaseSession
from rag.models import KnowledgeDocument, DocumentChunk, RetrievalLog


class RAGService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.chroma_dir = os.getenv("RAG_CHROMA_DIR", ".chroma")
        self.collection_name = os.getenv("RAG_COLLECTION_NAME", "autoaid_knowledge")
        self.chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))

        self.openai_client = OpenAI(api_key=self.api_key) if self.api_key else None

        self.collection = None
        try:
            Path(self.chroma_dir).mkdir(parents=True, exist_ok=True)
            chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
            self.collection = chroma_client.get_or_create_collection(name=self.collection_name)
        except Exception:
            # If vector store is unavailable, keyword fallback still works.
            self.collection = None

    # ---------- Public API ----------

    def ingest_document(self, doc: KnowledgeDocument) -> Dict[str, Any]:
        text = self._extract_document_text(doc)
        text = self._normalize_text(text)

        if len(text) < 50:
            raise ValueError("Document text is too short to index.")

        # Remove old chunks/vectors for re-indexing
        old_chunks = list(doc.chunks.all())
        old_vector_ids = [c.vector_id for c in old_chunks if c.vector_id]
        if self.collection and old_vector_ids:
            try:
                self.collection.delete(ids=old_vector_ids)
            except Exception:
                pass
        doc.chunks.all().delete()

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError("No chunks generated from document text.")

        # checksum
        doc.checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not doc.raw_text:
            # store first part for quick inspect; avoid huge DB rows
            doc.raw_text = text[:200000]
        doc.save(update_fields=["checksum", "raw_text", "updated_at"])

        created_rows: List[DocumentChunk] = []
        for idx, chunk in enumerate(chunks):
            created_rows.append(
                DocumentChunk(
                    document=doc,
                    chunk_index=idx,
                    content=chunk,
                    token_count=self._rough_token_count(chunk),
                    vector_id=None,
                    embedding_model=self.embedding_model if self.openai_client else "",
                    metadata={"len_chars": len(chunk)},
                )
            )

        DocumentChunk.objects.bulk_create(created_rows)
        db_chunks = list(doc.chunks.order_by("chunk_index"))

        vectors_indexed = 0
        embedding_mode = "keyword_only"

        # Try vector indexing (if possible)
        if self.openai_client and self.collection:
            try:
                embedding_mode = "vector+keyword_fallback"
                batch_size = 64
                for i in range(0, len(db_chunks), batch_size):
                    batch = db_chunks[i : i + batch_size]
                    texts = [c.content for c in batch]
                    embeddings = self._embed_texts(texts)

                    ids = []
                    metadatas = []
                    docs_text = []

                    for c in batch:
                        vector_id = f"{doc.id}:{c.chunk_index}:{uuid.uuid4().hex[:8]}"
                        c.vector_id = vector_id
                        ids.append(vector_id)
                        docs_text.append(c.content)
                        metadatas.append(
                            {
                                "document_id": str(doc.id),
                                "title": doc.title,
                                "source_type": doc.source_type,
                                "vehicle_make": (doc.vehicle_make or "").lower(),
                                "vehicle_model": (doc.vehicle_model or "").lower(),
                                "year_from": doc.year_from if doc.year_from is not None else -1,
                                "year_to": doc.year_to if doc.year_to is not None else -1,
                                "chunk_index": c.chunk_index,
                            }
                        )

                    self.collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=docs_text,
                        metadatas=metadatas,
                    )

                    DocumentChunk.objects.bulk_update(batch, ["vector_id"])
                    vectors_indexed += len(batch)
            except Exception:
                # keep keyword mode if vector indexing fails
                embedding_mode = "keyword_only"

        return {
            "document_id": str(doc.id),
            "title": doc.title,
            "chunks_created": len(db_chunks),
            "vectors_indexed": vectors_indexed,
            "embedding_mode": embedding_mode,
        }

    def retrieve(
        self,
        query_text: str,
        case: Optional[CaseSession] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        query_text = (query_text or "").strip()
        top_k = max(1, min(10, int(top_k)))

        citations: List[Dict[str, Any]] = []
        context_parts: List[str] = []
        used_vector = False

        # Try vector retrieval first
        if self.openai_client and self.collection:
            try:
                q_emb = self._embed_texts([query_text])[0]
                result = self.collection.query(
                    query_embeddings=[q_emb],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances", "ids"],
                )

                docs = ((result.get("documents") or [[]])[0]) or []
                metas = ((result.get("metadatas") or [[]])[0]) or []
                ids = ((result.get("ids") or [[]])[0]) or []
                distances = ((result.get("distances") or [[]])[0]) or []

                rows = []
                for i, doc_text in enumerate(docs):
                    meta = metas[i] if i < len(metas) else {}
                    vid = ids[i] if i < len(ids) else None
                    dist = distances[i] if i < len(distances) else None
                    rows.append((doc_text, meta, vid, dist))

                # Optional rerank by vehicle relevance
                rows = self._rerank_by_vehicle(rows, case)

                for i, (doc_text, meta, vid, dist) in enumerate(rows[:top_k]):
                    snippet = self._snippet(doc_text)
                    citation = {
                        "rank": i + 1,
                        "vector_id": vid,
                        "document_id": str(meta.get("document_id", "")),
                        "title": str(meta.get("title", "Knowledge Doc")),
                        "source_type": str(meta.get("source_type", "")),
                        "chunk_index": int(meta.get("chunk_index", -1)),
                        "distance": float(dist) if isinstance(dist, (int, float)) else None,
                        "snippet": snippet,
                    }
                    citations.append(citation)
                    context_parts.append(
                        f"[{i+1}] {citation['title']} (chunk {citation['chunk_index']}): {doc_text[:500]}"
                    )

                used_vector = len(citations) > 0
            except Exception:
                used_vector = False

        # Keyword fallback
        if not used_vector:
            citations, context_parts = self._keyword_retrieve(query_text=query_text, case=case, top_k=top_k)

        latency_ms = int((time.perf_counter() - started) * 1000)

        RetrievalLog.objects.create(
            case=case,
            query_text=query_text,
            top_k=top_k,
            retrieved_chunks=citations,
            reranked=bool(case),
            latency_ms=latency_ms,
        )

        return {
            "context_text": "\n\n".join(context_parts),
            "citations": citations,
            "latency_ms": latency_ms,
            "retrieval_mode": "vector" if used_vector else "keyword",
        }

    # ---------- Helpers ----------

    def _extract_document_text(self, doc: KnowledgeDocument) -> str:
        raw = (doc.raw_text or "").strip()
        file_text = ""

        if doc.file:
            doc.file.open("rb")
            try:
                suffix = Path(doc.file.name).suffix.lower()
                if suffix == ".pdf":
                    reader = PdfReader(doc.file)
                    pages = [p.extract_text() or "" for p in reader.pages]
                    file_text = "\n".join(pages)
                else:
                    content = doc.file.read()
                    file_text = content.decode("utf-8", errors="ignore")
            finally:
                doc.file.close()

        combined = "\n\n".join([x for x in [raw, file_text] if x])
        return combined

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(self, text: str) -> List[str]:
        size = max(300, self.chunk_size)
        overlap = min(max(50, self.chunk_overlap), size - 1)

        chunks: List[str] = []
        start = 0
        n = len(text)

        while start < n:
            end = min(start + size, n)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= n:
                break
            start = end - overlap

        return chunks

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client unavailable for embeddings.")
        resp = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    def _rough_token_count(self, text: str) -> int:
        # Approximation good enough for project telemetry
        return max(1, int(len(text) / 4))

    def _snippet(self, text: str, max_len: int = 220) -> str:
        t = self._normalize_text(text)
        return t[:max_len] + ("..." if len(t) > max_len else "")

    def _rerank_by_vehicle(self, rows: List[Tuple[Any, Any, Any, Any]], case: Optional[CaseSession]):
        if not case:
            return rows
        v_make = (case.vehicle.make or "").strip().lower()
        v_model = (case.vehicle.model or "").strip().lower()

        scored = []
        for row in rows:
            _, meta, _, dist = row
            score = 0
            m_make = str(meta.get("vehicle_make", "")).lower()
            m_model = str(meta.get("vehicle_model", "")).lower()

            if m_make and v_make and m_make == v_make:
                score += 2
            if m_model and v_model and m_model == v_model:
                score += 3

            # smaller distance is better
            dist_penalty = float(dist) if isinstance(dist, (int, float)) else 0.0
            scored.append((score - dist_penalty, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    def _keyword_retrieve(self, query_text: str, case: Optional[CaseSession], top_k: int):
        qs = DocumentChunk.objects.select_related("document").filter(document__is_active=True)

        if case:
            v = case.vehicle
            make = (v.make or "").strip()
            model = (v.model or "").strip()
            year = v.year

            make_q = Q(document__vehicle_make__exact="") | Q(document__vehicle_make__iexact=make)
            model_q = Q(document__vehicle_model__exact="") | Q(document__vehicle_model__iexact=model)
            yf_q = Q(document__year_from__isnull=True) | Q(document__year_from__lte=year)
            yt_q = Q(document__year_to__isnull=True) | Q(document__year_to__gte=year)

            qs = qs.filter(make_q & model_q & yf_q & yt_q)

        terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", query_text) if len(t) >= 3]
        if not terms:
            terms = query_text.lower().split()

        scored = []
        for ch in qs[:2000]:  # local cap for safety
            content_low = ch.content.lower()
            score = sum(content_low.count(t) for t in terms)
            if score > 0:
                scored.append((score, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        citations = []
        context_parts = []

        for i, (score, ch) in enumerate(top):
            citation = {
                "rank": i + 1,
                "vector_id": ch.vector_id,
                "document_id": str(ch.document_id),
                "title": ch.document.title,
                "source_type": ch.document.source_type,
                "chunk_index": ch.chunk_index,
                "distance": None,
                "score": score,
                "snippet": self._snippet(ch.content),
            }
            citations.append(citation)
            context_parts.append(f"[{i+1}] {ch.document.title} (chunk {ch.chunk_index}): {ch.content[:500]}")

        return citations, context_parts


rag_service = RAGService()
