"""
Pure domain functions for merchant / payee normalization.

Rules & Invariants:
1. Deterministic: Same relevant inputs -> same normalized merchant output.
2. Conservative: Prefer high precision over aggressive guessing; preserve cleaned text rather than inventing a merchant.
3. Precedence:
     manual override (handled at persistence/manager layer)
     > provider structured merchant (if provided)
     > normalized raw description candidate
4. Numbers that are part of a merchant identity (e.g. 7-Eleven, Studio 54, Super 8, Route 66, 76 Gas) are preserved.
5. Known acronyms (e.g. CVS, AMC, HEB, USAA, ACH) preserve uppercase formatting.
6. Pure: No ORM, no Session, no HTTP, no external network or environment calls.
"""

import re
from typing import Optional

ACRONYMS = frozenset({
    "ACH",
    "AMC",
    "AT&T",
    "ATM",
    "BMW",
    "BP",
    "CVS",
    "DMV",
    "HEB",
    "IBM",
    "IRS",
    "PGE",
    "PG&E",
    "UPS",
    "USAA",
})

CONNECTORS = frozenset({"and", "of", "the", "in", "on", "at", "to", "for", "&"})

COMMON_CITIES = (
    "SAN FRANCISCO|LOS ANGELES|NEW YORK|SEATTLE|AUSTIN|CHICAGO|BOSTON|PORTLAND|"
    "DENVER|DALLAS|HOUSTON|ATLANTA|MIAMI|PHOENIX|SAN DIEGO|LAS VEGAS|SALT LAKE CITY|"
    "MINNEAPOLIS|BROOKLYN|PHILADELPHIA|CHARLOTTE|NASHVILLE|ORLANDO|TAMPA|SACRAMENTO"
)

US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
)


def _title_case_word(index: int, word: str) -> str:
    upper = word.upper()
    lower = word.lower()
    if upper in ACRONYMS:
        return upper
    if lower == "paypal":
        return "PayPal"
    if lower == "ebay":
        return "eBay"
    if index > 0 and lower in CONNECTORS:
        return lower
    if "-" in word:
        return "-".join(_title_case_word(index, part) for part in word.split("-"))
    return word.capitalize()


def clean_casing(text: str) -> str:
    """
    Normalizes casing cleanly:
    - If all uppercase or all lowercase, converts to Title Case with acronym preservation.
    - If mixed case, preserves existing casing.
    """
    if not text:
        return text
    if text.isupper() or text.islower():
        words = text.split()
        if not words:
            return ""
        return " ".join(_title_case_word(i, w) for i, w in enumerate(words))
    return text


def normalize_merchant(
    raw_description: Optional[str],
    provider_merchant: Optional[str] = None,
) -> Optional[str]:
    """
    Turns noisy transaction descriptions / provider merchant data into a stable,
    human-readable merchant value.

    Precedence:
    1. If provider_merchant is given and non-empty, cleans whitespace/casing and returns it.
    2. Otherwise, cleans and extracts the merchant candidate from raw_description.
    """
    if provider_merchant is not None and provider_merchant.strip():
        pm = re.sub(r"\s+", " ", provider_merchant.strip())
        return clean_casing(pm)

    if raw_description is None or not raw_description.strip():
        return None

    s = re.sub(r"\s+", " ", raw_description.strip())

    # 1. Direct brand shortcuts supported by observed data
    if re.match(
        r"^(?:AMZN|AMAZON)(?:\s+MKTP|\.COM|\s+MARKETPLACE)?(?:\s+US)?(?:\*|\b).*",
        s,
        re.IGNORECASE,
    ):
        return "Amazon"

    # 2. PayPal with target merchant or standalone
    if re.match(r"^PAYPAL(?:\s*\*|\s+TRANSFER)?\s*$", s, re.IGNORECASE):
        return "PayPal"

    paypal_match = re.match(r"^PAYPAL\s*\*\s*(.+)$", s, re.IGNORECASE)
    if paypal_match:
        sub = paypal_match.group(1).strip()
        if sub:
            return normalize_merchant(sub)
        return "PayPal"

    # 3. Strip processor prefixes
    processor_prefixes = [
        r"^SQ\s*\*\s*",
        r"^SQR\s*\*\s*",
        r"^SQUARE\s*\*\s*",
        r"^TST\s*\*\s*",
        r"^TOAST\s*\*\s*",
        r"^SP\s*\*\s*",
        r"^STRIPE\s*\*\s*",
        r"^CHECKCARD(?:\s+\d+)?\s+",
        r"^POS\s+(?:DEBIT\s+)?",
        r"^DEBIT\s+CARD\s+",
        r"^PENDING\s*[-:]\s*",
        r"^DIRECT\s+DEPOSIT\s*[-–—:]\s*",
    ]
    for p in processor_prefixes:
        s = re.sub(p, "", s, flags=re.IGNORECASE).strip()

    # 4. Strip domain suffixes (.com, .org, .net)
    s = re.sub(r"\.(?:COM|ORG|NET)\b", "", s, flags=re.IGNORECASE).strip()

    # 5. Strip store/terminal numbers with STORE/UNIT or #
    s = re.sub(
        r"\s+(?:STORE|UNIT|LOC|LOCATION)\s*(?:#\s*|NO\.?\s*)?\d+\b.*$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    s = re.sub(r"\s+#\s*\d+\b.*$", "", s).strip()

    # 6. Strip store number followed by City + State
    s = re.sub(
        rf"\s+\d{{3,6}}\s+[A-Za-z\s]+?\s+(?:{US_STATES})\b$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()

    # 7. Strip known metropolitan City + State
    s = re.sub(
        rf"\s+(?:{COMMON_CITIES})\s+(?:{US_STATES})\b$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()

    # 8. Strip trailing 3-6 digit standalone store/terminal numbers
    s = re.sub(r"\s+\d{3,6}$", "", s).strip()

    # 9. Strip residual punctuation
    s = s.strip(" -*#:")

    if not s:
        return None

    return clean_casing(s)
