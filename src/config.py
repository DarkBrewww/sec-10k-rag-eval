"""Central configuration for the SEC RAG pipeline.

Anything tunable lives here, so the eval harness (later) can vary one
parameter at a time and we don't have to chase magic numbers across files.
"""
from pathlib import Path

# ----- Paths --------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # Raw EDGAR downloads
EXTRACTED_DIR = DATA_DIR / "extracted"  # Cleaned MD&A + Risk Factors text
CHROMA_DIR = DATA_DIR / "chroma"        # Vector store persistence

for _d in (DATA_DIR, RAW_DIR, EXTRACTED_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ----- Corpus scope (Week 1) ---------------------------------------------

COMPANIES = ["MSFT", "GOOGL", "META"]
# Filing calendar years to download. A 10-K filed in early 2024 typically
# reports on FY2023, so this gives us roughly 2 years of fiscal coverage.
YEARS = [2023, 2024]

# Sections we extract. Keys are the slugs we use everywhere downstream;
# values are the SEC item numbers.
SECTIONS = {
    "risk_factors": "1A",  # Item 1A. Risk Factors
    "mdna": "7",           # Item 7. Management's Discussion and Analysis
}

# ----- Models ------------------------------------------------------------

# Embeddings (OpenAI)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Generator (Anthropic). Haiku 4.5 is the Week 1 default: cheap and fast.
# We'll swap to Sonnet later and let the eval harness tell us if it's worth it.
GENERATOR_MODEL = "claude-haiku-4-5-20251001"

# Judge (Gemini). Not used until Week 3+. Free tier has ~15 RPM, ~1500 RPD.
# Cross-family from generator on purpose — reduces judge bias.
JUDGE_PROVIDER = "gemini"  # "gemini" | "anthropic" (fallback)
JUDGE_MODEL = "gemini-2.0-flash"
JUDGE_MODEL_FALLBACK = "claude-haiku-4-5-20251001"  # paid fallback when rate-limited

# Cost discipline (see docs/COST_DISCIPLINE.md). Hard ceilings.
DEFAULT_MAX_COST_USD = 0.50      # per eval run, dev mode
CI_MAX_COST_USD = 2.00           # per eval run in CI
DEFAULT_EVAL_SUBSET_SIZE = 20    # use --subset to override; full suite ~120

# ----- Chunking ----------------------------------------------------------

CHUNK_SIZE = 1000      # characters
CHUNK_OVERLAP = 200    # characters

# ----- Retrieval ---------------------------------------------------------

TOP_K = 5

# ----- Chroma ------------------------------------------------------------

COLLECTION_NAME = "sec_filings"

# ----- Generation prompt -------------------------------------------------

# Kept here (not in rag.py) so the eval harness can swap prompts cleanly
# and we can version-control prompt changes.
GENERATION_PROMPT = """You are answering questions about SEC 10-K filings. Follow these rules strictly:

1. Use ONLY the information in the provided context. Do not use outside knowledge, even if you are confident.
2. If the context does not contain enough information to answer, respond with exactly this sentence and nothing else: "I don't have enough information in the provided filings to answer this question."
3. Cite sources inline using [TICKER YEAR §section] notation after each factual claim. For example: "Microsoft's largest segment was Intelligent Cloud [MSFT 2023 §mdna]."
4. Be concise. 2-4 sentences unless the question genuinely requires more.

Context:
{context}

Question: {question}

Answer:"""

ABSTENTION_RESPONSE = "I don't have enough information in the provided filings to answer this question."
