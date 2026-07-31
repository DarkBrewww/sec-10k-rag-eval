"""CLI to query the RAG pipeline.

Usage:
    python -m scripts.ask "What risks did Meta disclose about AI competition in 2024?"
    python -m scripts.ask --top-k 8 "..."
    python -m scripts.ask --show-chunks "..."
"""
import argparse
import sys

from src.rag import answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask a question of the SEC RAG pipeline.")
    parser.add_argument("question", help="The question to ask.")
    parser.add_argument("--top-k", type=int, default=5, help="How many chunks to retrieve.")
    parser.add_argument(
        "--show-chunks",
        action="store_true",
        help="Print retrieved chunks too (useful for debugging retrieval quality).",
    )
    args = parser.parse_args()

    # Windows consoles default to cp1252, which mangles the section sign used in
    # chunk labels and citations. Force UTF-8 where the stream supports it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result = answer(args.question, top_k=args.top_k)

    if args.show_chunks:
        print("\n--- Retrieved chunks ---")
        for i, chunk in enumerate(result.retrieved, 1):
            m = chunk.metadata
            # `year` may be absent when the fiscal-year regex missed at extract time.
            year = m.get("year", "????")
            print(f"\n[{i}] {m['company']} FY{year} §{m['section']} "
                  f"(chunk #{m['chunk_index']}, score={chunk.score:.3f})")
            preview = chunk.content[:300].replace("\n", " ")
            print(f"    {preview}{'...' if len(chunk.content) > 300 else ''}")
        print("\n--- Answer ---")

    print(result.answer)
    if result.abstained:
        print("\n[note: the model abstained]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
