"""Download 10-K filings from SEC EDGAR.

EDGAR requires a user-agent identifying who you are. Set the
SEC_EDGAR_USER_AGENT environment variable in your .env file:

    SEC_EDGAR_USER_AGENT="Your Name your.email@example.com"
"""
import os

from dotenv import load_dotenv
from sec_edgar_downloader import Downloader

from . import config

load_dotenv()


def _parse_user_agent() -> tuple[str, str]:
    """Pull (name, email) from the user-agent env var."""
    ua = os.getenv("SEC_EDGAR_USER_AGENT", "")
    if " " in ua:
        name, email = ua.rsplit(" ", 1)
        return name.strip(), email.strip()
    # Fallback — EDGAR will probably still accept this but you should set it
    return "Researcher", "research@example.com"


def download_filings(companies=None, years=None) -> None:
    """Download 10-K filings for the configured companies and years.

    Files land under data/raw/sec-edgar-filings/<TICKER>/10-K/<accession>/.
    """
    companies = companies or config.COMPANIES
    years = years or config.YEARS

    name, email = _parse_user_agent()
    dl = Downloader(name, email, str(config.RAW_DIR))

    for ticker in companies:
        for year in years:
            # A 10-K filed in calendar year `year` reports on the fiscal year
            # that ended shortly before. Window is generous to handle non-
            # calendar fiscal years (Microsoft's FY ends in June, for example).
            print(f"[ingest] {ticker} 10-K filed in {year}...")
            try:
                dl.get(
                    "10-K",
                    ticker,
                    after=f"{year}-01-01",
                    before=f"{year}-12-31",
                    limit=1,
                )
            except Exception as e:
                # Don't let one company break the whole run
                print(f"[ingest]   failed: {e}")

    print(f"\n[ingest] done. Filings under {config.RAW_DIR}")


if __name__ == "__main__":
    download_filings()
