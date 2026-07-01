"""Chunk extracted sections, embed them, and store in Chroma.

Chunking is character-based with overlap — simpler than token-based and
sufficient for prose-heavy 10-K sections. The eval harness (later) will
tell us if we need to be smarter.
"""
# Defer annotation evaluation: chromadb >=1.0 exposes PersistentClient as a
# factory function (not a class), which breaks `PersistentClient | None`
# at module-load time without this.
from __future__ import annotations

import json
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from . import config

load_dotenv()


# Lazy singletons so importing this module doesn't require API keys.
_openai_client: OpenAI | None = None
_chroma_client: chromadb.PersistentClient | None = None


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def _chroma() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _chroma_client


# ----- Chunking ----------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence breaks.

    Walks the text in `chunk_size` windows. At each window, tries to back
    off to a nearby paragraph break, then a sentence break, before falling
    back to a hard character cut. Overlap is applied by stepping back
    `chunk_overlap` chars between chunks.
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            tail = text[start:].strip()
            if tail:
                chunks.append(tail)
            break

        # Prefer paragraph break in the back half of the window
        floor = start + chunk_size // 2
        break_at = text.rfind("\n\n", floor, end)
        if break_at == -1:
            # Fall back to sentence break
            break_at = text.rfind(". ", floor, end)
            offset = 2 if break_at != -1 else 0
        else:
            offset = 2  # include the \n\n

        if break_at == -1:
            break_at = end
            offset = 0

        chunk = text[start:break_at + offset].strip()
        if chunk:
            chunks.append(chunk)
        start = max(break_at + offset - chunk_overlap, start + 1)

    return chunks


# ----- Embedding --------------------------------------------------------

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings with the configured OpenAI model."""
    resp = _openai().embeddings.create(input=texts, model=config.EMBEDDING_MODEL)
    return [d.embedding for d in resp.data]


def _embed_all(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    out: list[list[float]] = []
    for i in tqdm(range(0, len(texts), batch_size), desc="embedding"):
        out.extend(embed_batch(texts[i:i + batch_size]))
    return out


# ----- Index build ------------------------------------------------------

def _load_extracted_records() -> list[dict]:
    """Load every extracted-section JSON from disk."""
    records: list[dict] = []
    for path in sorted(config.EXTRACTED_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            records.append(json.load(f))
    return records


def build_index(reset: bool = True) -> int:
    """Chunk + embed + store every extracted section. Returns chunk count.

    If `reset` is True, the existing collection is deleted first so the
    index reflects current data on disk only.
    """
    records = _load_extracted_records()
    if not records:
        print("[index] no extracted records found. Run extract first.")
        return 0

    client = _chroma()
    if reset:
        try:
            client.delete_collection(config.COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Build chunk-level rows across all records
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    for rec in records:
        chunks = chunk_text(rec["text"])
        for i, chunk in enumerate(chunks):
            chunk_id = f"{rec['company']}_{rec['fiscal_year']}_{rec['section']}_{i}"
            ids.append(chunk_id)
            docs.append(chunk)
            # chromadb 1.x rejects None in metadata values (Rust binding only
            # accepts str|int|float|bool). The fiscal-year regex can miss, so
            # drop the key when absent rather than crash the whole index build.
            meta = {
                "company": rec["company"],
                "section": rec["section"],
                "chunk_index": i,
                "accession": rec["accession"],
            }
            if rec["fiscal_year"] is not None:
                meta["year"] = rec["fiscal_year"]
            metas.append(meta)

    print(f"[index] embedding {len(docs)} chunks from {len(records)} sections...")
    embeddings = _embed_all(docs)

    # Chroma accepts up to a few thousand rows per add; batch defensively.
    BATCH = 500
    for i in range(0, len(ids), BATCH):
        collection.add(
            ids=ids[i:i + BATCH],
            embeddings=embeddings[i:i + BATCH],
            documents=docs[i:i + BATCH],
            metadatas=metas[i:i + BATCH],
        )

    print(f"[index] done. {len(ids)} chunks indexed in collection '{config.COLLECTION_NAME}'.")
    return len(ids)


def get_collection():
    """Open the existing Chroma collection (used by rag.py for retrieval)."""
    return _chroma().get_collection(config.COLLECTION_NAME)


if __name__ == "__main__":
    build_index()
