import csv
from dataclasses import dataclass
import io
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal, Optional

from backend.schemas import TransactionCreate


@dataclass(frozen=True)
class ParsedStatement:
    valid_transactions: tuple[TransactionCreate, ...]
    row_errors: tuple[str, ...]



class BankStatementLoader(ABC):
    """
    Abstract base class for parsing bank CSV exports into TransactionCreate objects.

    Subclasses define `column_map` (source col -> standard name) and `transform_row`
    to handle bank-specific date formats and amount sign conventions.
    """

    def __init__(self, account_id: UUID):
        self.account_id = account_id

    @property
    @abstractmethod
    def column_map(self):
        """Maps CSV column headers to internal standard names."""
        pass

    @classmethod
    def get_required_headers(cls) -> frozenset[str]:
        """Returns the frozenset of required CSV headers defined by column_map."""
        cmap = getattr(cls, "column_map", None)
        if isinstance(cmap, dict):
            return frozenset(cmap.keys())
        return frozenset()

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    def load_from_csv(self, filename: str) -> list[TransactionCreate]:
        """Load transactions from a CSV file path."""
        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        if path.suffix.lower() != ".csv":
            raise ValueError("File must be a CSV")

        with path.open("r", newline="", encoding="utf-8-sig") as f:
            return self._parse_stream(f)

    def load_from_text(self, content: str) -> list[TransactionCreate]:
        """Load transactions from CSV text content (e.g. from an HTTP upload)."""
        stream = io.StringIO(content)
        return self._parse_stream(stream)

    def load_from_bytes(self, raw: bytes, encoding: str = "utf-8-sig") -> list[TransactionCreate]:
        """Load transactions from raw bytes (e.g. from FastAPI UploadFile.read())."""
        return self.load_from_text(raw.decode(encoding))

    def load_records_tolerant(self, raw_bytes: bytes, encoding: str = "utf-8-sig") -> ParsedStatement:
        """
        Parse CSV bytes into valid TransactionCreate objects and row-level errors.

        Raises ValueError if required header columns are missing.
        Catches (ValueError, InvalidOperation, AttributeError, TypeError) per row and records them in row_errors.
        """
        text = raw_bytes.decode(encoding)
        stream = io.StringIO(text)
        reader = csv.DictReader(stream)

        if reader.fieldnames is not None:
            missing_columns = [
                col for col in self.column_map if col not in reader.fieldnames
            ]
            if missing_columns:
                raise ValueError(f"Missing columns: {missing_columns}")

        valid_transactions: list[TransactionCreate] = []
        row_errors: list[str] = []

        for i, raw_row in enumerate(reader, start=1):
            try:
                normalized_row = self.normalize_row(raw_row)
                txn = self.transform_row(normalized_row)
                if txn:
                    valid_transactions.append(txn)
            except (ValueError, InvalidOperation, AttributeError, TypeError) as exc:
                row_errors.append(f"Row {i}: {exc}")

        return ParsedStatement(
            valid_transactions=tuple(valid_transactions),
            row_errors=tuple(row_errors),
        )

    def _parse_stream(self, stream) -> list[TransactionCreate]:
        transactions = []
        reader = csv.DictReader(stream)

        for raw_row in reader:
            normalized_row = self.normalize_row(raw_row)
            transaction = self.transform_row(normalized_row)
            if transaction:
                transactions.append(transaction)

        return transactions

    # ------------------------------------------------------------------
    # Row normalization
    # ------------------------------------------------------------------

    def normalize_row(self, row: dict) -> dict:
        missing_columns = [
            source_name
            for source_name in self.column_map
            if source_name not in row
        ]

        if missing_columns:
            raise ValueError(f"Missing columns: {missing_columns}")

        return {
            standard_name: row[source_name].strip()
            for source_name, standard_name in self.column_map.items()
        }

    # ------------------------------------------------------------------
    # Abstract transform (bank-specific)
    # ------------------------------------------------------------------

    @abstractmethod
    def transform_row(self, row: dict) -> Optional[TransactionCreate]:
        """Convert a normalized row dict into a TransactionCreate schema."""
        pass


# ---------------------------------------------------------------------------
# Concrete loaders
# ---------------------------------------------------------------------------

class USAALoader(BankStatementLoader):
    """
    Parses USAA checking/savings CSV exports.

    Expected columns: Date, Description, Category, Amount, Status
    USAA exports amounts as negative for purchases, positive for deposits.
    We negate so that outflows are positive (app convention).
    """

    column_map = {
        "Date": "date",
        "Description": "description",
        "Category": "category",
        "Amount": "amount",
        "Status": "status",
    }

    def transform_row(self, row: dict) -> Optional[TransactionCreate]:
        amount = Decimal(row["amount"])
        pending = row["status"].lower() != "posted"

        return TransactionCreate(
            account_id=self.account_id,
            date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
            description=row["description"],
            amount=-amount,  # USAA: negative = outflow; we invert to positive = outflow
            pending=pending,
        )


class DiscoverLoader(BankStatementLoader):
    """
    Parses Discover credit card CSV exports.

    Expected columns: Trans. Date, Description, Amount, Category
    Discover exports charges as positive values.
    """

    column_map = {
        "Trans. Date": "date",
        "Description": "description",
        "Amount": "amount",
        "Category": "category",
    }

    def transform_row(self, row: dict) -> Optional[TransactionCreate]:
        amount = Decimal(row["amount"])

        return TransactionCreate(
            account_id=self.account_id,
            date=datetime.strptime(row["date"], "%m/%d/%Y").date(),
            description=row["description"],
            amount=amount,  # Discover: positive = charge (outflow) — matches app convention
            pending=False,
        )


# ---------------------------------------------------------------------------
# Configurable mapped loader
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MappedCSVFormatConfig:
    """
    Immutable parser configuration consumed by MappedStatementLoader to interpret
    user-defined/custom CSV statement exports.
    """
    date_column: str
    description_column: str
    amount_column: str

    date_format: str

    amount_sign_convention: Literal[
        "positive_is_outflow",
        "positive_is_inflow",
    ]

    status_column: Optional[str] = None
    status_posted_value: Optional[str] = None

    def __post_init__(self) -> None:
        if self.amount_sign_convention not in {
            "positive_is_outflow",
            "positive_is_inflow",
        }:
            raise ValueError(
                f"Invalid amount_sign_convention: {self.amount_sign_convention!r}. "
                "Must be 'positive_is_outflow' or 'positive_is_inflow'."
            )

        required_cols = [self.date_column, self.description_column, self.amount_column]
        if len(set(required_cols)) != 3:
            raise ValueError(
                "date_column, description_column, and amount_column must be distinct"
            )

        if self.status_column is not None and self.status_column in set(required_cols):
            raise ValueError(
                "status_column cannot be the same as date, description, or amount column"
            )

    @property
    def required_headers(self) -> frozenset[str]:
        """Returns the set of CSV source column names required by this configuration."""
        headers = [self.date_column, self.description_column, self.amount_column]
        if self.status_column:
            headers.append(self.status_column)
        return frozenset(headers)


class MappedStatementLoader(BankStatementLoader):
    """
    Concrete bank statement loader configured at runtime with dynamic column mappings,
    date formats, sign conventions, and status semantics via MappedCSVFormatConfig.
    """

    def __init__(self, account_id: UUID, config: MappedCSVFormatConfig):
        super().__init__(account_id=account_id)
        self.config = config

    @property
    def column_map(self) -> dict[str, str]:
        mapping = {
            self.config.date_column: "date",
            self.config.description_column: "description",
            self.config.amount_column: "amount",
        }
        if self.config.status_column:
            mapping[self.config.status_column] = "status"
        return mapping

    def transform_row(self, row: dict) -> Optional[TransactionCreate]:
        parsed_date = datetime.strptime(row["date"], self.config.date_format).date()
        amount = Decimal(row["amount"])

        if self.config.amount_sign_convention == "positive_is_inflow":
            amount = -amount

        if self.config.status_column:
            expected_posted = (self.config.status_posted_value or "posted").strip().lower()
            raw_status = row.get("status", "").strip().lower()
            pending = (raw_status != expected_posted)
        else:
            pending = False

        return TransactionCreate(
            account_id=self.account_id,
            date=parsed_date,
            description=row["description"],
            amount=amount,
            pending=pending,
        )


# ---------------------------------------------------------------------------
# Loader registry — maps format string to loader class
# ---------------------------------------------------------------------------

LOADER_REGISTRY: dict[str, type[BankStatementLoader]] = {
    "usaa": USAALoader,
    "discover": DiscoverLoader,
}


def get_loader(format_name: str, account_id: UUID) -> BankStatementLoader:
    """Instantiate the correct loader by format key."""
    cls = LOADER_REGISTRY.get(format_name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown format '{format_name}'. Available: {list(LOADER_REGISTRY)}"
        )
    return cls(account_id=account_id)


# ---------------------------------------------------------------------------
# Format definitions & detection (pure ingestion helpers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CSVFormatMatchDefinition:
    """
    Immutable metadata defining how an external CSV statement format is matched
    against uploaded CSV headers.
    """
    identifier: str
    name: str
    required_headers: frozenset[str]

    def __post_init__(self):
        if not isinstance(self.required_headers, frozenset):
            object.__setattr__(self, "required_headers", frozenset(self.required_headers))


@dataclass(frozen=True)
class FormatDetectionResult:
    """
    Immutable result of format detection against uploaded CSV headers.

    Status semantics:
    - 0 matches  -> 'unknown'
    - 1 match    -> 'detected'
    - 2+ matches -> 'ambiguous'
    """
    matches: tuple[CSVFormatMatchDefinition, ...]

    @property
    def status(self) -> Literal["unknown", "detected", "ambiguous"]:
        if not self.matches:
            return "unknown"
        if len(self.matches) == 1:
            return "detected"
        return "ambiguous"

    @property
    def detected_format(self) -> Optional[CSVFormatMatchDefinition]:
        """Returns the single detected format when status is 'detected', else None."""
        if len(self.matches) == 1:
            return self.matches[0]
        return None


def normalize_header(header: Optional[str]) -> str:
    """
    Normalizes a single CSV header: returns header string as-is, or empty string if None.
    Preserves exact whitespace, case, and punctuation to match parser contract.
    """
    if header is None:
        return ""
    return str(header)


def normalize_headers(headers: Sequence[Optional[str]]) -> tuple[str, ...]:
    """
    Normalizes a sequence of CSV header names preserving exact header text:
    - Preserves exact whitespace, case, and punctuation to match parser contract
    - Filters out empty or None headers
    """
    return tuple(str(h) for h in headers if h is not None and h != "")


def detect_csv_format(
    headers: Sequence[str],
    formats: Sequence[CSVFormatMatchDefinition],
) -> FormatDetectionResult:
    """
    Detects matching CSV format configurations for the given uploaded headers.

    Matching rule:
    A format matches when its required_headers are a subset of the normalized uploaded headers
    (i.e. format.required_headers <= normalized_uploaded_headers). Extra source columns are permitted.

    Ordering:
    Preserves the candidate ordering of the input `formats` sequence.
    """
    normalized_set = set(normalize_headers(headers))
    matches = [
        fmt for fmt in formats
        if fmt.required_headers.issubset(normalized_set)
    ]
    return FormatDetectionResult(matches=tuple(matches))


# ---------------------------------------------------------------------------
# Built-in format match metadata
# ---------------------------------------------------------------------------

USAA_FORMAT_MATCH = CSVFormatMatchDefinition(
    identifier="usaa",
    name="USAA",
    required_headers=USAALoader.get_required_headers(),
)

DISCOVER_FORMAT_MATCH = CSVFormatMatchDefinition(
    identifier="discover",
    name="Discover",
    required_headers=DiscoverLoader.get_required_headers(),
)

BUILTIN_FORMAT_MATCHES: tuple[CSVFormatMatchDefinition, ...] = (
    USAA_FORMAT_MATCH,
    DISCOVER_FORMAT_MATCH,
)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def main():
    import sys

    placeholder_id = uuid4()

    filename = "/Users/west/Downloads/bk_download.csv"
    loader = USAALoader(account_id=placeholder_id)
    transactions1 = loader.load_from_csv(filename)
    print(f"\nUSAA Transactions ({len(transactions1)} rows):")
    for t in transactions1[:5]:
        print(t)

    filename2 = "/Users/west/Downloads/Discover-RecentActivity-20260524.csv"
    loader2 = DiscoverLoader(account_id=placeholder_id)
    transactions2 = loader2.load_from_csv(filename2)
    print(f"\nDiscover Transactions ({len(transactions2)} rows):")
    for t in transactions2[:5]:
        print(t)


if __name__ == "__main__":
    main()
