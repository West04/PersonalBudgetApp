import csv
import io
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional

from backend.schemas import TransactionCreate


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
