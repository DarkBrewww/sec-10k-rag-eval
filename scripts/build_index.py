"""Build the entire pipeline end-to-end: download -> extract -> index.

Usage:
    python -m scripts.build_index
"""
from src.ingest import download_filings
from src.extract import extract_all
from src.index import build_index


def main() -> None:
    print("=" * 60)
    print("Step 1: Download 10-K filings from SEC EDGAR")
    print("=" * 60)
    download_filings()

    print("\n" + "=" * 60)
    print("Step 2: Extract MD&A and Risk Factors sections")
    print("=" * 60)
    records = extract_all()
    if not records:
        print("\nNo sections extracted. Check the data/raw/ directory and"
              " confirm EDGAR downloaded files. Aborting.")
        return

    print("\n" + "=" * 60)
    print("Step 3: Chunk, embed, and store in Chroma")
    print("=" * 60)
    n = build_index()

    print(f"\nDone. {n} chunks indexed.")
    print("Try: python -m scripts.ask \"What did Meta say about AI competition risks?\"")


if __name__ == "__main__":
    main()
