"""Retrieve relevant chunks and generate a grounded answer.

This is intentionally thin: one retrieve() function, one generate() function,
one answer() that composes them. The eval harness will call into these
pieces directly so it can measure retrieval and generation separately.
"""
from dataclasses import dataclass, field
from typing import Any

import anthropic
from dotenv import load_dotenv

from . import config
from .index import embed_batch, get_collection

load_dotenv()


_anthropic_client: anthropic.Anthropic | None = None


def _anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


@dataclass
class RetrievedChunk:
    content: str
    metadata: dict[str, Any]
    score: float  # cosine similarity, higher = better


@dataclass
class RagAnswer:
    question: str
    answer: str
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    abstained: bool = False
    model: str = ""


# ----- Retrieval --------------------------------------------------------

def retrieve(query: str, top_k: int = config.TOP_K) -> list[RetrievedChunk]:
    """Embed the query and pull the top-k chunks from Chroma."""
    collection = get_collection()
    [q_embedding] = embed_batch([query])

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=top_k,
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]  # cosine distance: lower = closer

    return [
        RetrievedChunk(content=d, metadata=m, score=1.0 - dist)
        for d, m, dist in zip(docs, metas, dists)
    ]


# ----- Generation -------------------------------------------------------

def _format_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks into the prompt context block."""
    parts = []
    for c in chunks:
        meta = c.metadata
        # `year` may be absent when the fiscal-year regex missed during
        # extraction; render a visible sentinel rather than crash, and so
        # the model's citations make the gap obvious.
        year = meta.get("year", "????")
        header = f"[{meta['company']} {year} §{meta['section']}]"
        parts.append(f"{header}\n{c.content}")
    return "\n\n---\n\n".join(parts)


def generate(query: str, chunks: list[RetrievedChunk]) -> str:
    """Call the configured LLM with the grounded prompt."""
    prompt = config.GENERATION_PROMPT.format(
        context=_format_context(chunks),
        question=query,
    )
    resp = _anthropic().messages.create(
        model=config.GENERATOR_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ----- End-to-end ------------------------------------------------------

def answer(query: str, top_k: int = config.TOP_K) -> RagAnswer:
    """Full retrieve -> generate pipeline. Returns a structured answer."""
    chunks = retrieve(query, top_k=top_k)
    text = generate(query, chunks)
    return RagAnswer(
        question=query,
        answer=text,
        retrieved=chunks,
        abstained=config.ABSTENTION_RESPONSE in text,
        model=config.GENERATOR_MODEL,
    )
