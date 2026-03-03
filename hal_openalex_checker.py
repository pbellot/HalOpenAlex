"""
HAL-OpenAlex Checker
====================
For a given laboratory (identified by its HAL structId), retrieves all
publications from the last 10 years (metadata only) and checks whether
each one is also present in OpenAlex.

Usage:
    python hal_openalex_checker.py --struct-id 441569
    python hal_openalex_checker.py --struct-id 441569 --years 5 --output results.json

HAL API:    https://api.archives-ouvertes.fr/search/
OpenAlex:   https://api.openalex.org/works
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HAL_SEARCH_URL = "https://api.archives-ouvertes.fr/search/"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

# Fields retrieved from HAL (metadata only, no full-text)
HAL_FIELDS = ",".join(
    [
        "docid",
        "halId_s",
        "uri_s",
        "title_s",
        "doi_s",
        "authFullName_s",
        "producedDate_tdate",
        "submittedDate_tdate",
        "docType_s",
        "journalTitle_s",
    ]
)

# Maximum rows per HAL request
HAL_PAGE_SIZE = 100

# Polite delay between OpenAlex requests (seconds)
OPENALEX_DELAY = 0.1


# ---------------------------------------------------------------------------
# HAL helpers
# ---------------------------------------------------------------------------


def fetch_hal_publications(struct_id: int, years: int = 10) -> list[dict]:
    """Return all publications for *struct_id* published in the last *years* years.

    Uses cursor-based pagination to retrieve all results.

    Args:
        struct_id: HAL structure (laboratory) identifier.
        years: Number of years to look back from today.

    Returns:
        A list of dicts, each containing the metadata fields for one publication.
    """
    start_year = date.today().year - years
    date_filter = f"producedDate_tdate:[{start_year}-01-01T00:00:00Z TO *]"

    params = {
        "q": f"structId_i:{struct_id}",
        "fq": date_filter,
        "fl": HAL_FIELDS,
        "rows": HAL_PAGE_SIZE,
        "start": 0,
        "wt": "json",
        "sort": "producedDate_tdate desc",
    }

    publications = []
    total = None

    while True:
        response = requests.get(HAL_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        response_body = data.get("response", {})
        if total is None:
            total = response_body.get("numFound", 0)

        docs = response_body.get("docs", [])
        if not docs:
            break

        publications.extend(docs)

        params["start"] += len(docs)
        if params["start"] >= total:
            break

    return publications


# ---------------------------------------------------------------------------
# OpenAlex helpers
# ---------------------------------------------------------------------------


def _openalex_by_doi(doi: str, email: Optional[str] = None) -> Optional[dict]:
    """Look up a single work in OpenAlex by DOI.

    Args:
        doi: The DOI string (with or without the ``https://doi.org/`` prefix).
        email: Optional e-mail address for the polite pool.

    Returns:
        The OpenAlex work dict, or *None* if not found.
    """
    # Normalise DOI to a bare identifier (no URL prefix)
    clean_doi = doi.strip()
    clean_doi = clean_doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")

    params: dict = {"filter": f"doi:{clean_doi}", "select": "id,doi,title"}
    if email:
        params["mailto"] = email

    resp = requests.get(OPENALEX_WORKS_URL, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def _openalex_by_title(title: str, email: Optional[str] = None) -> Optional[dict]:
    """Look up a work in OpenAlex by title (fuzzy search).

    Args:
        title: Publication title string.
        email: Optional e-mail address for the polite pool.

    Returns:
        The best-matching OpenAlex work dict, or *None* if not found.
    """
    params: dict = {
        "search": title,
        "select": "id,doi,title",
        "per_page": 1,
    }
    if email:
        params["mailto"] = email

    resp = requests.get(OPENALEX_WORKS_URL, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def check_in_openalex(
    publication: dict, email: Optional[str] = None
) -> dict:
    """Check whether a HAL publication is present in OpenAlex.

    First tries to match by DOI; falls back to title search when no DOI is
    available.

    Args:
        publication: A HAL publication metadata dict.
        email: Optional e-mail for OpenAlex polite pool.

    Returns:
        A result dict with keys:
            ``hal_id``      – HAL identifier
            ``title``       – publication title
            ``doi``         – DOI (or ``None``)
            ``found``       – ``True`` if the work was found in OpenAlex
            ``match_type``  – ``"doi"``, ``"title"``, or ``None``
            ``openalex_id`` – OpenAlex work URL (or ``None``)
    """
    hal_id = publication.get("halId_s", publication.get("docid", ""))
    titles = publication.get("title_s", [])
    title = titles[0] if titles else ""
    dois = publication.get("doi_s", [])
    doi = dois[0] if dois else None

    result: dict = {
        "hal_id": hal_id,
        "title": title,
        "doi": doi,
        "found": False,
        "match_type": None,
        "openalex_id": None,
    }

    oa_work = None
    if doi:
        oa_work = _openalex_by_doi(doi, email=email)
        if oa_work:
            result["match_type"] = "doi"

    if oa_work is None and title:
        oa_work = _openalex_by_title(title, email=email)
        if oa_work:
            result["match_type"] = "title"

    if oa_work:
        result["found"] = True
        result["openalex_id"] = oa_work.get("id")

    time.sleep(OPENALEX_DELAY)
    return result


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def run(
    struct_id: int,
    years: int = 10,
    email: Optional[str] = None,
    output: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """Execute the full HAL → OpenAlex check for a laboratory.

    Args:
        struct_id: HAL structure identifier for the laboratory.
        years: Number of years to look back.
        email: Optional e-mail address for OpenAlex polite pool.
        output: Optional file path to write the JSON results.
        verbose: Print progress to stderr.

    Returns:
        A summary dict with keys ``struct_id``, ``years``, ``run_date``,
        ``total``, ``found``, ``not_found``, and ``results``.
    """
    if verbose:
        print(f"Fetching HAL publications for structId={struct_id} …", file=sys.stderr)

    publications = fetch_hal_publications(struct_id, years=years)

    if verbose:
        print(
            f"  {len(publications)} publication(s) retrieved. Checking OpenAlex …",
            file=sys.stderr,
        )

    results = []
    for i, pub in enumerate(publications, start=1):
        result = check_in_openalex(pub, email=email)
        results.append(result)
        if verbose:
            status = "✓" if result["found"] else "✗"
            print(
                f"  [{i}/{len(publications)}] {status} {result['hal_id']} – {result['title'][:60]}",
                file=sys.stderr,
            )

    found_count = sum(1 for r in results if r["found"])
    summary = {
        "struct_id": struct_id,
        "years": years,
        "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(results),
        "found": found_count,
        "not_found": len(results) - found_count,
        "results": results,
    }

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        if verbose:
            print(f"Results written to {output}", file=sys.stderr)

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check which HAL publications of a laboratory are also present in OpenAlex."
        )
    )
    parser.add_argument(
        "--struct-id",
        required=True,
        type=int,
        metavar="ID",
        help="HAL structure identifier for the laboratory (structId_i).",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=10,
        metavar="N",
        help="Number of years to look back (default: 10).",
    )
    parser.add_argument(
        "--email",
        default=None,
        metavar="EMAIL",
        help="E-mail address for the OpenAlex polite pool (optional but recommended).",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write JSON results to FILE instead of stdout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information to stderr.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    summary = run(
        struct_id=args.struct_id,
        years=args.years,
        email=args.email,
        output=args.output,
        verbose=args.verbose,
    )

    if args.output is None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
