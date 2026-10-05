"""
Unit tests for pure domain merchant normalization Engine (backend/domain/merchant_normalization.py).

Verifies:
1. Observed processor prefixes (Square, Toast, Stripe, PayPal, CheckCard, Pending, Direct Deposit).
2. Store and terminal numbers (#123, STORE 440, trailing 3-6 digits).
3. Location suffixes (City + State).
4. Acronym preservation (CVS, AMC, HEB, USAA, ACH).
5. False-positive guards: numbers that are part of merchant identity (7-Eleven, Studio 54, Super 8, Route 66, 76 Gas, Five Guys, Blink-182, A1).
6. Mixed-casing preservation and Title Casing of ALL-CAPS.
7. Idempotency: normalize(normalize(x)) == normalize(x).
8. Provider structured merchant precedence over raw description.
9. Conservative fallback on unknown/unparseable text.
"""

import pytest
from backend.domain.merchant_normalization import (
    normalize_merchant,
    clean_casing,
)


# ---------------------------------------------------------------------------
# 1. Observed Processor Prefixes & Brand Patterns
# ---------------------------------------------------------------------------

def test_square_processor_prefix_removal():
    assert normalize_merchant("SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA") == "Blue Bottle"
    assert normalize_merchant("SQ *JOES COFFEE #4821") == "Joes Coffee"
    assert normalize_merchant("SQR* LOCAL CAFE") == "Local Cafe"
    assert normalize_merchant("SQUARE * ARTISAN BAKERY") == "Artisan Bakery"


def test_toast_processor_prefix_removal():
    assert normalize_merchant("TST* CHIPOTLE 1234") == "Chipotle"
    assert normalize_merchant("TST* TACO DEL MAR #12") == "Taco Del Mar"
    assert normalize_merchant("TOAST * PIZZA PLACE") == "Pizza Place"


def test_paypal_processor_prefix_removal():
    assert normalize_merchant("PAYPAL *NETFLIX") == "Netflix"
    assert normalize_merchant("PAYPAL *SPOTIFY") == "Spotify"
    assert normalize_merchant("PAYPAL * STEAM GAMES") == "Steam Games"
    assert normalize_merchant("PAYPAL *") == "PayPal"


def test_stripe_processor_prefix_removal():
    assert normalize_merchant("SP * SUBSTACK") == "Substack"
    assert normalize_merchant("STRIPE * NOTION") == "Notion"


def test_checkcard_and_pos_prefix_removal():
    assert normalize_merchant("CHECKCARD 1004 STARBUCKS 1234") == "Starbucks"
    assert normalize_merchant("CHECKCARD SAFEWAY") == "Safeway"
    assert normalize_merchant("POS DEBIT GROCERY OUTLET") == "Grocery Outlet"
    assert normalize_merchant("DEBIT CARD CORNER STORE") == "Corner Store"


def test_pending_and_deposit_prefix_removal():
    assert normalize_merchant("PENDING - BEST BUY") == "Best Buy"
    assert normalize_merchant("PENDING - UBER EATS") == "Uber Eats"
    assert normalize_merchant("PENDING: DOCTOR VISIT") == "Doctor Visit"
    assert normalize_merchant("DIRECT DEPOSIT - ACME CORP") == "Acme Corp"


def test_amazon_shortcuts():
    assert normalize_merchant("AMZN Mktp US*AB12CD34") == "Amazon"
    assert normalize_merchant("AMAZON.COM") == "Amazon"
    assert normalize_merchant("AMAZON MARKETPLACE") == "Amazon"
    assert normalize_merchant("AMZN.COM") == "Amazon"
    assert normalize_merchant("AMAZON MKTP") == "Amazon"


# ---------------------------------------------------------------------------
# 2. Store / Terminal Numbers & Domain Suffixes
# ---------------------------------------------------------------------------

def test_store_and_terminal_number_removal():
    assert normalize_merchant("WHOLE FOODS #123") == "Whole Foods"
    assert normalize_merchant("TRADER JOES #456") == "Trader Joes"
    assert normalize_merchant("SAFEWAY #789") == "Safeway"
    assert normalize_merchant("STARBUCKS STORE 440") == "Starbucks"
    assert normalize_merchant("TARGET STORE #1042") == "Target"
    assert normalize_merchant("WALMART SUPERCENTER #2041") == "Walmart Supercenter"


def test_domain_suffix_removal():
    assert normalize_merchant("NETFLIX.COM") == "Netflix"
    assert normalize_merchant("SPOTIFY.COM") == "Spotify"
    assert normalize_merchant("WIKIPEDIA.ORG") == "Wikipedia"


# ---------------------------------------------------------------------------
# 3. Location Suffixes (City + State)
# ---------------------------------------------------------------------------

def test_location_suffix_removal():
    assert normalize_merchant("BLUE BOTTLE SAN FRANCISCO CA") == "Blue Bottle"
    assert normalize_merchant("TORCHYS TACOS AUSTIN TX") == "Torchys Tacos"
    assert normalize_merchant("PIKE PLACE FISH SEATTLE WA") == "Pike Place Fish"


# ---------------------------------------------------------------------------
# 4. Acronym Preservation & Title Casing
# ---------------------------------------------------------------------------

def test_acronym_preservation():
    assert normalize_merchant("HEB GROCERY") == "HEB Grocery"
    assert normalize_merchant("CVS PHARMACY") == "CVS Pharmacy"
    assert normalize_merchant("AMC THEATRES") == "AMC Theatres"
    assert normalize_merchant("USAA INSURANCE") == "USAA Insurance"
    assert normalize_merchant("PACIFIC GAS & ELECTRIC") == "Pacific Gas & Electric"


def test_case_normalization_and_preservation():
    # ALL-CAPS converts to Title Case
    assert normalize_merchant("CHIPOTLE") == "Chipotle"
    assert normalize_merchant("BARNES AND NOBLE") == "Barnes and Noble"

    # All-lowercase converts to Title Case
    assert normalize_merchant("starbucks") == "Starbucks"

    # Mixed-case is preserved
    assert normalize_merchant("McDonald's") == "McDonald's"
    assert normalize_merchant("Trader Joe's") == "Trader Joe's"
    assert normalize_merchant("Payment from Client A") == "Payment from Client A"


# ---------------------------------------------------------------------------
# 5. False-Positive Protection (Numbers in Merchant Identity)
# ---------------------------------------------------------------------------

def test_false_positive_numbers_preserved():
    assert normalize_merchant("7-Eleven") == "7-Eleven"
    assert normalize_merchant("7-ELEVEN #4012") == "7-Eleven"
    assert normalize_merchant("WAL-MART #1234") == "Wal-Mart"
    assert normalize_merchant("Studio 54") == "Studio 54"
    assert normalize_merchant("Super 8") == "Super 8"
    assert normalize_merchant("Route 66") == "Route 66"
    assert normalize_merchant("76 Gas") == "76 Gas"
    assert normalize_merchant("Five Guys") == "Five Guys"
    assert normalize_merchant("Blink-182") == "Blink-182"
    assert normalize_merchant("A1") == "A1"


# ---------------------------------------------------------------------------
# 6. Conservative Fallback on Unknown / Non-Merchant Text
# ---------------------------------------------------------------------------

def test_conservative_fallback_on_unparsed_text():
    # Does not guess Amazon or other random brands
    assert normalize_merchant("ACH WEB PAYMENT 493028") == "ACH Web Payment"
    assert normalize_merchant("Consulting Invoice #1042") == "Consulting Invoice"
    assert normalize_merchant("CHECK #1042") == "Check"
    assert normalize_merchant("UNKNOWN VENDOR #12345") == "Unknown Vendor"


# ---------------------------------------------------------------------------
# 7. Idempotency Invariant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_input",
    [
        "SQ *BLUE BOTTLE 12345 SAN FRANCISCO CA",
        "TST* CHIPOTLE 1234",
        "AMZN Mktp US*AB12CD34",
        "PAYPAL *NETFLIX",
        "CHECKCARD 1004 STARBUCKS 1234",
        "HEB GROCERY",
        "CVS PHARMACY",
        "AMC THEATRES",
        "7-Eleven",
        "Studio 54",
        "Route 66",
        "Super 8",
        "76 Gas",
        "Barnes and Noble",
        "Payment from Client A",
    ],
)
def test_normalization_idempotency(raw_input: str):
    first_pass = normalize_merchant(raw_input)
    assert first_pass is not None
    second_pass = normalize_merchant(first_pass)
    assert second_pass == first_pass


# ---------------------------------------------------------------------------
# 8. Provider Structured Merchant Precedence
# ---------------------------------------------------------------------------

def test_provider_structured_merchant_precedence():
    # Provider merchant takes precedence over raw description
    assert (
        normalize_merchant("PAYPAL *UNKNOWN123", provider_merchant="Netflix")
        == "Netflix"
    )
    assert (
        normalize_merchant("SQ *SOME NOISY RAW #999", provider_merchant="Blue Bottle Coffee")
        == "Blue Bottle Coffee"
    )
    # If provider merchant is ALL-CAPS, cleans casing cleanly
    assert (
        normalize_merchant("RAW DESC", provider_merchant="WHOLE FOODS MARKET")
        == "Whole Foods Market"
    )
    # If provider merchant is empty/whitespace, falls back to raw description
    assert (
        normalize_merchant("TST* CHIPOTLE 1234", provider_merchant="")
        == "Chipotle"
    )
    assert (
        normalize_merchant("TST* CHIPOTLE 1234", provider_merchant="   ")
        == "Chipotle"
    )
    assert (
        normalize_merchant("TST* CHIPOTLE 1234", provider_merchant=None)
        == "Chipotle"
    )


# ---------------------------------------------------------------------------
# 9. Empty and None Inputs
# ---------------------------------------------------------------------------

def test_empty_and_none_inputs():
    assert normalize_merchant(None) is None
    assert normalize_merchant("") is None
    assert normalize_merchant("   ") is None
    assert normalize_merchant("   ---   ") is None
