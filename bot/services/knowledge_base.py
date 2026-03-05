"""Векторная база знаний на Chroma + синхронизация с Notion."""
import logging
import asyncio
from typing import List, Dict, Optional
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800      # символов в одном чанке
CHUNK_OVERLAP = 100   # перекрытие между чанками
TOP_K = 4             # сколько релевантных чанков передавать в Claude


class KnowledgeBase:
    def __init__(self, persist_dir: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Бесплатные embeddings через sentence-transformers (работает локально)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"  # поддерживает русский
        )
        self.collection = self.client.get_or_create_collection(
            name="human2035",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Knowledge base loaded: {self.collection.count()} chunks")

    def _chunk_text(self, text: str, doc_id: str, title: str, url: str) -> List[Dict]:
        """Разбить текст на чанки с метаданными."""
        chunks = []
        start = 0
        idx = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]
            if chunk.strip():
                chunks.append({
                    "id": f"{doc_id}_chunk_{idx}",
                    "text": chunk,
                    "metadata": {"title": title, "url": url, "doc_id": doc_id, "chunk": idx},
                })
            start = end - CHUNK_OVERLAP
            idx += 1
        return chunks

    def add_documents(self, documents: List[Dict]):
        """Добавить/обновить документы в базе знаний."""
        all_chunks = []
        for doc in documents:
            chunks = self._chunk_text(
                text=doc["content"],
                doc_id=doc["id"],
                title=doc["title"],
                url=doc.get("url", ""),
            )
            all_chunks.extend(chunks)

        if not all_chunks:
            return

        # Загружаем батчами по 100
        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            self.collection.upsert(
                ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
            )

        logger.info(f"Indexed {len(all_chunks)} chunks from {len(documents)} documents")

    def search(self, query: str, n_results: int = TOP_K) -> str:
        """Найти релевантные чанки и вернуть как контекст для Claude."""
        count = self.collection.count()
        if count == 0:
            return ""

        results = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )

        chunks = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not chunks:
            return ""

        context_parts = []
        seen_docs = set()
        for chunk, meta in zip(chunks, metas):
            title = meta.get("title", "")
            doc_id = meta.get("doc_id", "")
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                context_parts.append(f"[Источник: {title}]\n{chunk}")
            else:
                context_parts.append(chunk)

        return "\n\n---\n\n".join(context_parts)

    def get_stats(self) -> dict:
        return {"total_chunks": self.collection.count()}

    def clear(self):
        """Очистить базу (для полной пересинхронизации)."""
        self.client.delete_collection("human2035")
        self.collection = self.client.get_or_create_collection(
            name="human2035",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )


# Глобальный инстанс (инициализируется при старте)
kb: Optional[KnowledgeBase] = None


def get_kb() -> Optional[KnowledgeBase]:
    return kb


async def init_knowledge_base(persist_dir: str = None):
    global kb
    from config.settings import settings
    path = persist_dir or settings.CHROMA_PERSIST_DIR
    loop = asyncio.get_event_loop()
    kb = await loop.run_in_executor(None, lambda: KnowledgeBase(path))
    logger.info("Knowledge base initialized")
    return kb
