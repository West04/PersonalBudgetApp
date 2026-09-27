from dataclasses import FrozenInstanceError
from uuid import uuid4
import pytest

from backend.bank_statement_loader import (
    BankStatementLoader,
    USAALoader,
    DiscoverLoader,
    CSVFormatMatchDefinition,
    FormatDetectionResult,
    normalize_header,
    normalize_headers,
    detect_csv_format,
    USAA_FORMAT_MATCH,
    DISCOVER_FORMAT_MATCH,
    BUILTIN_FORMAT_MATCHES,
)


# ---------------------------------------------------------------------------
# Metadata & Loader Contract Tests
# ---------------------------------------------------------------------------

def test_loader_class_method_derives_required_headers():
    """Verify get_required_headers directly derives from column_map on the loader classes."""
    assert USAALoader.get_required_headers() == frozenset(USAALoader.column_map.keys())
    assert DiscoverLoader.get_required_headers() == frozenset(DiscoverLoader.column_map.keys())
    assert USAALoader.get_required_headers() == frozenset({
        "Date", "Description", "Category", "Amount", "Status"
    })
    assert DiscoverLoader.get_required_headers() == frozenset({
        "Trans. Date", "Description", "Amount", "Category"
    })


def test_builtin_usaa_match_definition():
    """Verify USAA_FORMAT_MATCH contains only detection metadata matching USAALoader."""
    assert USAA_FORMAT_MATCH.identifier == "usaa"
    assert USAA_FORMAT_MATCH.name == "USAA"
    assert USAA_FORMAT_MATCH.required_headers == frozenset({
        "Date", "Description", "Category", "Amount", "Status"
    })


def test_builtin_discover_match_definition():
    """Verify DISCOVER_FORMAT_MATCH contains only detection metadata matching DiscoverLoader."""
    assert DISCOVER_FORMAT_MATCH.identifier == "discover"
    assert DISCOVER_FORMAT_MATCH.name == "Discover"
    assert DISCOVER_FORMAT_MATCH.required_headers == frozenset({
        "Trans. Date", "Description", "Amount", "Category"
    })


def test_builtin_format_matches_collection():
    """Verify BUILTIN_FORMAT_MATCHES contains exactly the built-in detection definitions."""
    assert BUILTIN_FORMAT_MATCHES == (
        USAA_FORMAT_MATCH,
        DISCOVER_FORMAT_MATCH,
    )
    assert isinstance(BUILTIN_FORMAT_MATCHES, tuple)


def test_csv_format_match_definition_immutability():
    """Verify CSVFormatMatchDefinition is a frozen dataclass."""
    defn = CSVFormatMatchDefinition(
        identifier="custom",
        name="Custom",
        required_headers=frozenset({"A", "B", "C"}),
    )
    with pytest.raises(FrozenInstanceError):
        defn.name = "Mutated"  # type: ignore


def test_csv_format_match_definition_converts_set_to_frozenset():
    """Verify CSVFormatMatchDefinition automatically converts iterable required_headers to frozenset."""
    defn = CSVFormatMatchDefinition(
        identifier="custom",
        name="Custom",
        required_headers={"A", "B", "C"},  # type: ignore[arg-type]
    )
    assert isinstance(defn.required_headers, frozenset)
    assert defn.required_headers == frozenset({"A", "B", "C"})


# ---------------------------------------------------------------------------
# Header Normalization Tests (Parser-Aligned: Exact Text Preserved)
# ---------------------------------------------------------------------------

def test_normalize_header_preserves_exact_text():
    """Header text is preserved verbatim without stripping whitespace or changing case."""
    assert normalize_header(" Date ") == " Date "
    assert normalize_header("Trans. Date") == "Trans. Date"
    assert normalize_header("DESCRIPTION") == "DESCRIPTION"
    assert normalize_header("") == ""
    assert normalize_header(None) == ""


def test_normalize_headers_preserves_whitespace_and_case():
    raw = [" Date ", "Trans. Date", "CATEGORY", "Amount ($)", "Status"]
    expected = (" Date ", "Trans. Date", "CATEGORY", "Amount ($)", "Status")
    assert normalize_headers(raw) == expected


def test_normalize_headers_filters_empty_and_none():
    raw = ["", "Date", None, "Amount"]  # type: ignore[list-item]
    assert normalize_headers(raw) == ("Date", "Amount")


# ---------------------------------------------------------------------------
# Detection Tests — USAA
# ---------------------------------------------------------------------------

def test_detect_usaa_exact_headers():
    """Exact USAA headers match USAA and produce 'detected' status."""
    headers = ["Date", "Description", "Category", "Amount", "Status"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "detected"
    assert len(result.matches) == 1
    assert result.matches[0] == USAA_FORMAT_MATCH
    assert result.detected_format == USAA_FORMAT_MATCH


def test_detect_usaa_missing_category_is_unknown():
    """
    USAA loader structurally requires Category.
    A file missing Category must NOT match USAA and produces 'unknown'.
    """
    headers = ["Date", "Description", "Amount", "Status"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()
    assert result.detected_format is None


def test_detect_usaa_extra_columns():
    """Subset matching allows extra columns and matches USAA."""
    headers = [
        "Date", "Description", "Category", "Amount", "Status",
        "Memo", "Reference Number"
    ]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "detected"
    assert len(result.matches) == 1
    assert result.matches[0] == USAA_FORMAT_MATCH
    assert result.detected_format == USAA_FORMAT_MATCH


def test_detect_usaa_with_surrounding_whitespace_is_unknown():
    """
    Align with parser contract: the loader does not strip header whitespace.
    Therefore, headers with surrounding whitespace do NOT match USAA.
    """
    headers = [" Date ", " Description ", " Category ", " Amount ", " Status "]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()


def test_detect_usaa_case_sensitive():
    """
    CSV headers remain case-sensitive under current parser contract.
    Lowercased headers do not match USAA.
    """
    headers = ["date", "description", "category", "amount", "status"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()


def test_detect_usaa_with_empty_headers_present():
    """Empty headers in uploaded list are filtered out and do not prevent matching valid headers."""
    headers = ["", "Date", "Description", "Category", "Amount", "Status"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "detected"
    assert result.matches[0] == USAA_FORMAT_MATCH


def test_detect_usaa_with_utf8_bom_decoded_via_utf8_sig():
    """
    In the real upload pipeline, BOM is stripped at byte-decode time via utf-8-sig.
    When bytes with BOM are decoded using utf-8-sig, the resulting headers match USAA.
    """
    raw_csv = "\ufeffDate,Description,Category,Amount,Status\n".encode("utf-8")
    decoded_text = raw_csv.decode("utf-8-sig")
    import csv, io
    reader = csv.DictReader(io.StringIO(decoded_text))
    headers = reader.fieldnames or []

    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)
    assert result.status == "detected"
    assert result.matches[0] == USAA_FORMAT_MATCH


# ---------------------------------------------------------------------------
# Detection Tests — Discover
# ---------------------------------------------------------------------------

def test_detect_discover_exact_headers():
    """Exact Discover headers match Discover and produce 'detected' status."""
    headers = ["Trans. Date", "Description", "Amount", "Category"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "detected"
    assert len(result.matches) == 1
    assert result.matches[0] == DISCOVER_FORMAT_MATCH
    assert result.detected_format == DISCOVER_FORMAT_MATCH


def test_detect_discover_missing_category_is_unknown():
    """Discover loader structurally requires Category. Missing Category fails."""
    headers = ["Trans. Date", "Description", "Amount"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()


def test_detect_discover_extra_columns():
    """Extra columns with Discover headers still detect Discover."""
    headers = ["Trans. Date", "Post Date", "Description", "Amount", "Category", "Memo"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "detected"
    assert result.matches[0] == DISCOVER_FORMAT_MATCH


def test_detect_discover_with_surrounding_whitespace_is_unknown():
    """Discover headers with surrounding whitespace are rejected to match parser."""
    headers = [" Trans. Date ", "Description", "Amount", "Category"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()


# ---------------------------------------------------------------------------
# Detection Tests — Unknown
# ---------------------------------------------------------------------------

def test_detect_unknown_format():
    """Unrecognized headers produce 'unknown' status."""
    headers = ["Date", "Memo", "Value"]
    result = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()
    assert result.detected_format is None


def test_detect_empty_headers_list():
    """Empty headers sequence produces 'unknown' status."""
    result = detect_csv_format([], BUILTIN_FORMAT_MATCHES)

    assert result.status == "unknown"
    assert result.matches == ()
    assert result.detected_format is None


# ---------------------------------------------------------------------------
# Detection Tests — Ambiguity & Ordering
# ---------------------------------------------------------------------------

def test_detect_ambiguous_custom_formats():
    """
    Two custom definitions with identical required headers both match the
    same uploaded headers, producing 'ambiguous' status.
    Distinguished only by identifier and name; no parser configuration needed.
    """
    custom_a = CSVFormatMatchDefinition(
        identifier="custom-a",
        name="Custom Format A",
        required_headers=frozenset({"Date", "Description", "Amount"}),
    )
    custom_b = CSVFormatMatchDefinition(
        identifier="custom-b",
        name="Custom Format B",
        required_headers=frozenset({"Date", "Description", "Amount"}),
    )

    formats = [custom_a, custom_b]
    headers = ["Date", "Description", "Amount"]

    result = detect_csv_format(headers, formats)

    assert result.status == "ambiguous"
    assert result.matches == (custom_a, custom_b)
    assert result.detected_format is None


def test_detect_builtin_and_custom_collision_is_ambiguous():
    """
    When uploaded headers match both a built-in format and a broader custom format,
    detection returns 'ambiguous' without silently favoring the built-in format.
    """
    broader_custom = CSVFormatMatchDefinition(
        identifier="broad-custom",
        name="Broad Custom",
        required_headers=frozenset({"Date", "Description", "Amount"}),
    )

    formats = [USAA_FORMAT_MATCH, broader_custom]
    # Full USAA headers satisfy both USAA (all 5) and broader_custom (3 subset)
    headers = ["Date", "Description", "Category", "Amount", "Status"]

    result = detect_csv_format(headers, formats)

    assert result.status == "ambiguous"
    assert len(result.matches) == 2
    assert result.matches == (USAA_FORMAT_MATCH, broader_custom)
    assert result.detected_format is None


def test_detect_preserves_input_candidate_ordering():
    """
    When multiple candidates match, the output matches tuple strictly preserves
    the ordering of the input candidate formats.
    """
    custom_1 = CSVFormatMatchDefinition(
        identifier="c1",
        name="Custom 1",
        required_headers=frozenset({"Date", "Description", "Amount"}),
    )
    custom_2 = CSVFormatMatchDefinition(
        identifier="c2",
        name="Custom 2",
        required_headers=frozenset({"Date", "Amount"}),
    )

    headers = ["Date", "Description", "Amount"]

    # Order: [custom_1, custom_2]
    res1 = detect_csv_format(headers, [custom_1, custom_2])
    assert res1.matches == (custom_1, custom_2)

    # Reversed order: [custom_2, custom_1]
    res2 = detect_csv_format(headers, [custom_2, custom_1])
    assert res2.matches == (custom_2, custom_1)


# ---------------------------------------------------------------------------
# Detector / Loader Alignment Tests (Contract Guarantee)
# ---------------------------------------------------------------------------

def test_detector_parser_alignment_accepted_headers():
    """
    Prove that headers accepted by detect_csv_format for USAA
    are accepted without missing-column error by USAALoader.
    """
    headers = ["Date", "Description", "Category", "Amount", "Status", "ExtraColumn"]
    res = detect_csv_format(headers, BUILTIN_FORMAT_MATCHES)
    assert res.status == "detected"
    assert res.detected_format == USAA_FORMAT_MATCH

    # Pass CSV with these exact headers to USAALoader
    csv_bytes = (
        b"Date,Description,Category,Amount,Status,ExtraColumn\n"
        b"2026-05-15,HEB GROCERY,Food,-85.42,posted,extra_val\n"
    )
    loader = USAALoader(account_id=uuid4())
    parsed = loader.load_records_tolerant(csv_bytes)
    assert len(parsed.valid_transactions) == 1
    assert parsed.valid_transactions[0].description == "HEB GROCERY"


def test_detector_parser_alignment_rejected_headers():
    """
    Prove that header sets rejected by USAALoader (whitespace or case mismatch)
    are also rejected (not positively identified) by detect_csv_format.
    """
    account_id = uuid4()
    loader = USAALoader(account_id=account_id)

    # 1. Whitespace mismatch
    ws_headers = [" Date ", "Description", "Category", "Amount", "Status"]
    res_ws = detect_csv_format(ws_headers, BUILTIN_FORMAT_MATCHES)
    assert res_ws.status == "unknown"

    csv_ws = b" Date ,Description,Category,Amount,Status\n2026-05-15,STORE,Food,-10.00,posted\n"
    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_records_tolerant(csv_ws)

    # 2. Case mismatch
    case_headers = ["date", "Description", "Category", "Amount", "Status"]
    res_case = detect_csv_format(case_headers, BUILTIN_FORMAT_MATCHES)
    assert res_case.status == "unknown"

    csv_case = b"date,Description,Category,Amount,Status\n2026-05-15,STORE,Food,-10.00,posted\n"
    with pytest.raises(ValueError, match="Missing columns"):
        loader.load_records_tolerant(csv_case)
