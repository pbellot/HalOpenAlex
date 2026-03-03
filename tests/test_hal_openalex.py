"""
Unit tests for hal_openalex_checker.py
All HTTP calls are mocked so the tests run without network access.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

import hal_openalex_checker as checker


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_HAL_DOC_WITH_DOI = {
    "docid": "123456",
    "halId_s": "hal-123456",
    "uri_s": "https://hal.science/hal-123456",
    "title_s": ["A great paper"],
    "doi_s": ["10.1000/xyz123"],
    "authFullName_s": ["Alice Author"],
    "producedDate_tdate": "2022-01-01T00:00:00Z",
    "docType_s": "ART",
}

SAMPLE_HAL_DOC_NO_DOI = {
    "docid": "789012",
    "halId_s": "hal-789012",
    "uri_s": "https://hal.science/hal-789012",
    "title_s": ["Another great paper"],
    "doi_s": [],
    "authFullName_s": ["Bob Builder"],
    "producedDate_tdate": "2021-06-15T00:00:00Z",
    "docType_s": "COMM",
}

SAMPLE_HAL_DOC_NO_TITLE_NO_DOI = {
    "docid": "000001",
    "halId_s": "hal-000001",
    "title_s": [],
    "doi_s": [],
}

OPENALEX_WORK = {
    "id": "https://openalex.org/W123456",
    "doi": "https://doi.org/10.1000/xyz123",
    "title": "A great paper",
}


def _hal_response(docs: list, num_found: int | None = None) -> MagicMock:
    """Build a mock requests.Response for the HAL API."""
    if num_found is None:
        num_found = len(docs)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": {
            "numFound": num_found,
            "docs": docs,
        }
    }
    return mock_resp


def _oa_response(results: list) -> MagicMock:
    """Build a mock requests.Response for the OpenAlex API."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"results": results}
    return mock_resp


# ---------------------------------------------------------------------------
# Tests: fetch_hal_publications
# ---------------------------------------------------------------------------


class TestFetchHalPublications:
    @patch("hal_openalex_checker.requests.get")
    def test_returns_docs_single_page(self, mock_get):
        mock_get.return_value = _hal_response([SAMPLE_HAL_DOC_WITH_DOI])
        docs = checker.fetch_hal_publications(struct_id=12345, years=10)
        assert len(docs) == 1
        assert docs[0]["halId_s"] == "hal-123456"

    @patch("hal_openalex_checker.requests.get")
    def test_paginates_when_many_results(self, mock_get):
        page1 = [SAMPLE_HAL_DOC_WITH_DOI] * checker.HAL_PAGE_SIZE
        page2 = [SAMPLE_HAL_DOC_NO_DOI] * 5
        total = checker.HAL_PAGE_SIZE + 5

        mock_get.side_effect = [
            _hal_response(page1, num_found=total),
            _hal_response(page2, num_found=total),
        ]

        docs = checker.fetch_hal_publications(struct_id=12345, years=10)
        assert len(docs) == total
        assert mock_get.call_count == 2

    @patch("hal_openalex_checker.requests.get")
    def test_returns_empty_list_when_no_docs(self, mock_get):
        mock_get.return_value = _hal_response([], num_found=0)
        docs = checker.fetch_hal_publications(struct_id=99999, years=10)
        assert docs == []

    @patch("hal_openalex_checker.requests.get")
    def test_year_filter_uses_correct_start_year(self, mock_get):
        from datetime import date

        mock_get.return_value = _hal_response([])
        checker.fetch_hal_publications(struct_id=12345, years=5)
        params = mock_get.call_args.kwargs["params"]
        expected_year = date.today().year - 5
        assert str(expected_year) in params["fq"]

    @patch("hal_openalex_checker.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        mock_get.return_value = mock_resp
        with pytest.raises(Exception, match="HTTP 500"):
            checker.fetch_hal_publications(struct_id=12345, years=10)


# ---------------------------------------------------------------------------
# Tests: check_in_openalex
# ---------------------------------------------------------------------------


class TestCheckInOpenalex:
    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_found_by_doi(self, mock_get, mock_sleep):
        mock_get.return_value = _oa_response([OPENALEX_WORK])
        result = checker.check_in_openalex(SAMPLE_HAL_DOC_WITH_DOI)
        assert result["found"] is True
        assert result["match_type"] == "doi"
        assert result["openalex_id"] == OPENALEX_WORK["id"]
        assert result["hal_id"] == "hal-123456"
        assert result["doi"] == "10.1000/xyz123"

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_found_by_title_when_no_doi(self, mock_get, mock_sleep):
        mock_get.return_value = _oa_response([OPENALEX_WORK])
        result = checker.check_in_openalex(SAMPLE_HAL_DOC_NO_DOI)
        assert result["found"] is True
        assert result["match_type"] == "title"
        assert result["doi"] is None

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_not_found_when_doi_and_title_both_miss(self, mock_get, mock_sleep):
        mock_get.return_value = _oa_response([])
        result = checker.check_in_openalex(SAMPLE_HAL_DOC_WITH_DOI)
        assert result["found"] is False
        assert result["match_type"] is None
        assert result["openalex_id"] is None

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_falls_back_to_title_when_doi_not_found(self, mock_get, mock_sleep):
        # First call (DOI lookup) returns nothing; second call (title) returns a result
        mock_get.side_effect = [
            _oa_response([]),       # DOI lookup: no result
            _oa_response([OPENALEX_WORK]),  # title lookup: found
        ]
        result = checker.check_in_openalex(SAMPLE_HAL_DOC_WITH_DOI)
        assert result["found"] is True
        assert result["match_type"] == "title"

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_not_found_when_no_title_and_no_doi(self, mock_get, mock_sleep):
        result = checker.check_in_openalex(SAMPLE_HAL_DOC_NO_TITLE_NO_DOI)
        assert result["found"] is False
        mock_get.assert_not_called()

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_doi_with_url_prefix_is_normalised(self, mock_get, mock_sleep):
        doc = {**SAMPLE_HAL_DOC_WITH_DOI, "doi_s": ["https://doi.org/10.1000/xyz123"]}
        mock_get.return_value = _oa_response([OPENALEX_WORK])
        result = checker.check_in_openalex(doc)
        assert result["found"] is True
        # Verify the DOI passed to OpenAlex does not include the URL prefix
        params = mock_get.call_args[1]["params"]
        assert "https://doi.org/" not in params["filter"]

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_email_forwarded_to_openalex(self, mock_get, mock_sleep):
        mock_get.return_value = _oa_response([OPENALEX_WORK])
        checker.check_in_openalex(SAMPLE_HAL_DOC_WITH_DOI, email="test@example.com")
        params = mock_get.call_args[1]["params"]
        assert params.get("mailto") == "test@example.com"

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_sleep_is_called_after_openalex_request(self, mock_get, mock_sleep):
        mock_get.return_value = _oa_response([])
        checker.check_in_openalex(SAMPLE_HAL_DOC_WITH_DOI)
        mock_sleep.assert_called_once_with(checker.OPENALEX_DELAY)


# ---------------------------------------------------------------------------
# Tests: run (integration-level, all HTTP mocked)
# ---------------------------------------------------------------------------


class TestRun:
    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_summary_counts(self, mock_get, mock_sleep):
        hal_response = _hal_response(
            [SAMPLE_HAL_DOC_WITH_DOI, SAMPLE_HAL_DOC_NO_DOI], num_found=2
        )
        oa_found = _oa_response([OPENALEX_WORK])
        oa_not_found = _oa_response([])

        mock_get.side_effect = [
            hal_response,   # HAL
            oa_found,       # OpenAlex DOI lookup for doc 1
            oa_not_found,   # OpenAlex title lookup for doc 2
        ]

        summary = checker.run(struct_id=12345, years=10)
        assert summary["total"] == 2
        assert summary["found"] == 1
        assert summary["not_found"] == 1
        assert summary["struct_id"] == 12345
        assert summary["years"] == 10

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_output_written_to_file(self, mock_get, mock_sleep, tmp_path):
        mock_get.side_effect = [
            _hal_response([SAMPLE_HAL_DOC_WITH_DOI]),
            _oa_response([OPENALEX_WORK]),
        ]
        out_file = str(tmp_path / "results.json")
        checker.run(struct_id=12345, output=out_file)
        with open(out_file, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["total"] == 1
        assert data["found"] == 1

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_run_date_is_iso_format(self, mock_get, mock_sleep):
        mock_get.return_value = _hal_response([])
        summary = checker.run(struct_id=12345)
        # Should not raise
        datetime.strptime(summary["run_date"], "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------


class TestCLI:
    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_cli_prints_json_to_stdout(self, mock_get, mock_sleep, capsys):
        mock_get.side_effect = [
            _hal_response([SAMPLE_HAL_DOC_WITH_DOI]),
            _oa_response([OPENALEX_WORK]),
        ]
        checker.main(["--struct-id", "12345"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["struct_id"] == 12345
        assert data["total"] == 1

    @patch("hal_openalex_checker.time.sleep")
    @patch("hal_openalex_checker.requests.get")
    def test_cli_years_argument(self, mock_get, mock_sleep):
        mock_get.return_value = _hal_response([])
        checker.main(["--struct-id", "12345", "--years", "5"])
        from datetime import date

        expected_year = date.today().year - 5
        params = mock_get.call_args.kwargs["params"]
        assert str(expected_year) in params["fq"]

    def test_cli_missing_struct_id_exits(self):
        with pytest.raises(SystemExit):
            checker.main([])
