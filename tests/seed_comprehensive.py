#!/usr/bin/env python3
"""
Comprehensive seed script for the Budget App.

Seeds the database with realistic test data covering:
- Category groups and categories (income, expense, transfer types)
- Multiple accounts (checking, savings, credit cards)
- Transactions spanning multiple months (categorized, uncategorized, pending)
- Budget entries for multiple months

Usage:
    python tests/seed_comprehensive.py [--base-url URL]

Default URL: http://127.0.0.1:12344
"""

import argparse
import requests
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

DEFAULT_BASE_URL = "http://127.0.0.1:12344"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def log_success(msg: str):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")


def log_section(msg: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def log_info(msg: str):
    print(f"{Colors.YELLOW}→{Colors.RESET} {msg}")


class BudgetSeeder:
    def __init__(self, base_url: str, clean: bool = False):
        self.base_url = base_url.rstrip("/")
        self.clean = clean
        self.groups: dict[str, str] = {}  # name -> id
        self.categories: dict[str, str] = {}  # name -> id
        self.accounts: dict[str, str] = {}  # name -> id
        self.transactions: list[str] = []
        self.budgets: list[str] = []

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make a POST request and return JSON response."""
        try:
            r = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=10)
            if r.status_code in (200, 201):
                return r.json()
            else:
                log_error(f"POST {endpoint} failed: {r.status_code} - {r.text[:200]}")
                return None
        except requests.RequestException as e:
            log_error(f"POST {endpoint} error: {e}")
            return None

    def _get(self, endpoint: str) -> Optional[dict]:
        """Make a GET request and return JSON response."""
        try:
            r = requests.get(f"{self.base_url}{endpoint}", timeout=10)
            if r.status_code == 200:
                return r.json()
            return None
        except requests.RequestException:
            return None

    def _delete(self, endpoint: str) -> bool:
        """Make a DELETE request."""
        try:
            r = requests.delete(f"{self.base_url}{endpoint}", timeout=10)
            return r.status_code in (200, 204)
        except requests.RequestException:
            return False

    def clear_existing_data(self):
        """Clear existing data if --clean flag is set."""
        if not self.clean:
            return

        log_section("Clearing Existing Data")

        # Delete transactions first (they reference accounts and categories)
        transactions = self._get("/transactions/")
        if transactions and "items" in transactions:
            for txn in transactions["items"]:
                if self._delete(f"/transactions/{txn['transaction_id']}"):
                    log_success(f"Deleted transaction: {txn['description'][:30]}")
            log_info(f"Deleted {len(transactions['items'])} transactions")

        # Delete budgets
        budgets = self._get("/budget/")
        if budgets:
            for b in budgets:
                if self._delete(f"/budget/{b['budget_id']}"):
                    pass
            log_info(f"Deleted {len(budgets)} budgets")

        # Delete accounts
        accounts = self._get("/accounts/")
        if accounts:
            for acc in accounts:
                if self._delete(f"/accounts/{acc['account_id']}"):
                    log_success(f"Deleted account: {acc['name']}")
            log_info(f"Deleted {len(accounts)} accounts")

        # Note: We don't delete categories/groups as they may be system defaults

    def seed_category_groups(self):
        """Create category groups for organizing categories."""
        log_section("Seeding Category Groups")

        groups = [
            {"name": "Income", "sort_order": 0},
            {"name": "Housing", "sort_order": 1},
            {"name": "Food & Dining", "sort_order": 2},
            {"name": "Transportation", "sort_order": 3},
            {"name": "Utilities", "sort_order": 4},
            {"name": "Healthcare", "sort_order": 5},
            {"name": "Personal", "sort_order": 6},
            {"name": "Entertainment", "sort_order": 7},
            {"name": "Savings & Debt", "sort_order": 8},
            {"name": "Transfers", "sort_order": 9},
        ]

        for g in groups:
            result = self._post("/category-groups", g)
            if result:
                self.groups[g["name"]] = result["category_group_id"]
                log_success(f"Created group: {g['name']}")
            else:
                # Try to fetch existing
                existing = self._get("/category-groups")
                if existing:
                    for eg in existing:
                        if eg["name"] == g["name"]:
                            self.groups[g["name"]] = eg["category_group_id"]
                            log_info(f"Using existing group: {g['name']}")
                            break

        log_info(f"Total groups available: {len(self.groups)}")

    def seed_categories(self):
        """Create categories within each group."""
        log_section("Seeding Categories")

        # First, fetch existing categories
        existing_categories = self._get("/categories") or []
        for cat in existing_categories:
            self.categories[cat["name"]] = cat["category_id"]

        if existing_categories:
            log_info(f"Found {len(existing_categories)} existing categories")

        categories = [
            # Income categories
            {"name": "Salary", "group": "Income", "type": "income"},
            {"name": "Freelance", "group": "Income", "type": "income"},
            {"name": "Interest & Dividends", "group": "Income", "type": "income"},
            {"name": "Other Income", "group": "Income", "type": "income"},

            # Housing
            {"name": "Rent/Mortgage", "group": "Housing", "type": "expense"},
            {"name": "Home Insurance", "group": "Housing", "type": "expense"},
            {"name": "Property Tax", "group": "Housing", "type": "expense"},
            {"name": "Home Maintenance", "group": "Housing", "type": "expense"},

            # Food & Dining
            {"name": "Groceries", "group": "Food & Dining", "type": "expense"},
            {"name": "Restaurants", "group": "Food & Dining", "type": "expense"},
            {"name": "Coffee Shops", "group": "Food & Dining", "type": "expense"},
            {"name": "Fast Food", "group": "Food & Dining", "type": "expense"},

            # Transportation
            {"name": "Gas", "group": "Transportation", "type": "expense"},
            {"name": "Car Payment", "group": "Transportation", "type": "expense"},
            {"name": "Car Insurance", "group": "Transportation", "type": "expense"},
            {"name": "Car Maintenance", "group": "Transportation", "type": "expense"},
            {"name": "Public Transit", "group": "Transportation", "type": "expense"},
            {"name": "Parking", "group": "Transportation", "type": "expense"},

            # Utilities
            {"name": "Electricity", "group": "Utilities", "type": "expense"},
            {"name": "Water", "group": "Utilities", "type": "expense"},
            {"name": "Internet", "group": "Utilities", "type": "expense"},
            {"name": "Phone", "group": "Utilities", "type": "expense"},
            {"name": "Gas (Utility)", "group": "Utilities", "type": "expense"},

            # Healthcare
            {"name": "Health Insurance", "group": "Healthcare", "type": "expense"},
            {"name": "Doctor Visits", "group": "Healthcare", "type": "expense"},
            {"name": "Pharmacy", "group": "Healthcare", "type": "expense"},
            {"name": "Dental", "group": "Healthcare", "type": "expense"},

            # Personal
            {"name": "Clothing", "group": "Personal", "type": "expense"},
            {"name": "Haircuts", "group": "Personal", "type": "expense"},
            {"name": "Gym Membership", "group": "Personal", "type": "expense"},
            {"name": "Personal Care", "group": "Personal", "type": "expense"},

            # Entertainment
            {"name": "Streaming Services", "group": "Entertainment", "type": "expense"},
            {"name": "Movies & Events", "group": "Entertainment", "type": "expense"},
            {"name": "Hobbies", "group": "Entertainment", "type": "expense"},
            {"name": "Games", "group": "Entertainment", "type": "expense"},
            {"name": "Books", "group": "Entertainment", "type": "expense"},

            # Savings & Debt
            {"name": "Emergency Fund", "group": "Savings & Debt", "type": "expense"},
            {"name": "Retirement", "group": "Savings & Debt", "type": "expense"},
            {"name": "Credit Card Payment", "group": "Savings & Debt", "type": "expense"},
            {"name": "Student Loans", "group": "Savings & Debt", "type": "expense"},

            # Transfers
            {"name": "Transfer to Savings", "group": "Transfers", "type": "transfer"},
            {"name": "Transfer to Checking", "group": "Transfers", "type": "transfer"},
        ]

        sort_order_by_group: dict[str, int] = {}
        created_count = 0

        for c in categories:
            # Skip if category already exists
            if c["name"] in self.categories:
                continue

            group_id = self.groups.get(c["group"])
            if not group_id:
                log_error(f"Group '{c['group']}' not found for category '{c['name']}'")
                continue

            sort_order = sort_order_by_group.get(c["group"], 0)
            sort_order_by_group[c["group"]] = sort_order + 1

            payload = {
                "name": c["name"],
                "group_id": group_id,
                "type": c["type"],
                "sort_order": sort_order,
                "is_active": True,
            }

            result = self._post("/categories", payload)
            if result:
                self.categories[c["name"]] = result["category_id"]
                log_success(f"Created category: {c['name']} ({c['type']})")
                created_count += 1

        log_info(f"Created {created_count} new categories, total available: {len(self.categories)}")

    def seed_accounts(self):
        """Create various account types."""
        log_section("Seeding Accounts")

        # Fetch existing accounts
        existing_accounts = self._get("/accounts/") or []
        for acc in existing_accounts:
            self.accounts[acc["name"]] = acc["account_id"]

        if existing_accounts:
            log_info(f"Found {len(existing_accounts)} existing accounts")

        accounts = [
            {
                "name": "Primary Checking",
                "type": "depository",
                "subtype": "checking",
                "current_balance": 3542.67,
                "currency": "USD",
            },
            {
                "name": "Savings Account",
                "type": "depository",
                "subtype": "savings",
                "current_balance": 12500.00,
                "currency": "USD",
            },
            {
                "name": "Chase Credit Card",
                "type": "credit",
                "subtype": "credit card",
                "current_balance": -1234.56,  # Negative = owed
                "currency": "USD",
            },
            {
                "name": "Amex Platinum",
                "type": "credit",
                "subtype": "credit card",
                "current_balance": -567.89,
                "currency": "USD",
            },
            {
                "name": "Investment Account",
                "type": "investment",
                "subtype": "brokerage",
                "current_balance": 45000.00,
                "currency": "USD",
            },
        ]

        created_count = 0
        for acc in accounts:
            # Skip if account already exists
            if acc["name"] in self.accounts:
                continue

            result = self._post("/accounts/", acc)
            if result:
                self.accounts[acc["name"]] = result["account_id"]
                log_success(f"Created account: {acc['name']} (${acc['current_balance']:,.2f})")
                created_count += 1

        log_info(f"Created {created_count} new accounts, total available: {len(self.accounts)}")

    def seed_transactions(self):
        """Create transactions spanning multiple months with various scenarios."""
        log_section("Seeding Transactions")

        today = date.today()
        checking_id = self.accounts.get("Primary Checking")
        savings_id = self.accounts.get("Savings Account")
        chase_cc_id = self.accounts.get("Chase Credit Card")
        amex_id = self.accounts.get("Amex Platinum")

        if not checking_id:
            log_error("Primary Checking account not found - skipping transactions")
            return

        # Generate transactions for the past 3 months
        transactions = []

        # Helper to create a transaction dict
        def txn(account_id, amount, days_ago, description, category_name=None, pending=False):
            return {
                "account_id": account_id,
                "amount": amount,
                "date": str(today - timedelta(days=days_ago)),
                "description": description,
                "category_id": self.categories.get(category_name) if category_name else None,
                "pending": pending,
            }

        # ===== INCOME TRANSACTIONS (negative amounts = inflow) =====
        # Monthly salary deposits
        for month_offset in range(3):
            days_ago = month_offset * 30 + 1
            transactions.append(txn(checking_id, -5000.00, days_ago, "DIRECT DEPOSIT - ACME CORP", "Salary"))
            transactions.append(txn(checking_id, -5000.00, days_ago + 14, "DIRECT DEPOSIT - ACME CORP", "Salary"))

        # Freelance income
        transactions.append(txn(checking_id, -750.00, 5, "Payment from Client A", "Freelance"))
        transactions.append(txn(checking_id, -1200.00, 35, "Consulting Invoice #1042", "Freelance"))

        # Interest
        transactions.append(txn(savings_id, -12.50, 2, "INTEREST PAYMENT", "Interest & Dividends"))
        transactions.append(txn(savings_id, -11.75, 32, "INTEREST PAYMENT", "Interest & Dividends"))

        # ===== HOUSING =====
        for month_offset in range(3):
            days_ago = month_offset * 30 + 3
            transactions.append(txn(checking_id, 1850.00, days_ago, "LUXURY APARTMENTS - RENT", "Rent/Mortgage"))

        transactions.append(txn(checking_id, 125.00, 45, "HOME DEPOT - MAINTENANCE", "Home Maintenance"))

        # ===== FOOD & DINING =====
        grocery_stores = ["WHOLE FOODS", "TRADER JOES", "SAFEWAY", "COSTCO", "TARGET"]
        restaurants = ["CHIPOTLE", "OLIVE GARDEN", "MCDONALDS", "STARBUCKS", "PANERA BREAD"]

        for i in range(15):
            store = random.choice(grocery_stores)
            amount = round(random.uniform(35, 180), 2)
            transactions.append(txn(checking_id, amount, i * 5, f"{store} #{random.randint(100,999)}", "Groceries"))

        for i in range(20):
            restaurant = random.choice(restaurants)
            amount = round(random.uniform(8, 65), 2)
            account = random.choice([checking_id, chase_cc_id, amex_id])
            if account:
                cat = "Coffee Shops" if "STARBUCKS" in restaurant else "Restaurants"
                transactions.append(txn(account, amount, i * 3, f"{restaurant}", cat))

        # ===== TRANSPORTATION =====
        gas_stations = ["SHELL", "CHEVRON", "76", "EXXON"]
        for i in range(8):
            station = random.choice(gas_stations)
            amount = round(random.uniform(35, 70), 2)
            transactions.append(txn(checking_id, amount, i * 10 + 2, f"{station} GAS", "Gas"))

        # Car payment (monthly)
        for month_offset in range(3):
            days_ago = month_offset * 30 + 10
            transactions.append(txn(checking_id, 425.00, days_ago, "TOYOTA FINANCIAL SERVICES", "Car Payment"))

        transactions.append(txn(chase_cc_id, 85.00, 25, "JIFFY LUBE - OIL CHANGE", "Car Maintenance"))
        transactions.append(txn(checking_id, 150.00, 60, "DISCOUNT TIRE", "Car Maintenance"))

        # ===== UTILITIES =====
        for month_offset in range(3):
            base_days = month_offset * 30
            transactions.append(txn(checking_id, round(random.uniform(80, 150), 2), base_days + 5, "PACIFIC GAS & ELECTRIC", "Electricity"))
            transactions.append(txn(checking_id, round(random.uniform(30, 50), 2), base_days + 8, "CITY WATER DEPT", "Water"))

        transactions.append(txn(checking_id, 79.99, 12, "COMCAST INTERNET", "Internet"))
        transactions.append(txn(checking_id, 85.00, 15, "VERIZON WIRELESS", "Phone"))

        # ===== HEALTHCARE =====
        transactions.append(txn(checking_id, 350.00, 20, "KAISER PERMANENTE", "Health Insurance"))
        transactions.append(txn(chase_cc_id, 25.00, 40, "CVS PHARMACY", "Pharmacy"))
        transactions.append(txn(checking_id, 150.00, 55, "DR SMITH MEDICAL", "Doctor Visits"))

        # ===== PERSONAL =====
        transactions.append(txn(amex_id, 125.00, 10, "NORDSTROM", "Clothing"))
        transactions.append(txn(chase_cc_id, 45.00, 22, "AMAZON.COM", "Clothing"))
        transactions.append(txn(checking_id, 50.00, 30, "PLANET FITNESS", "Gym Membership"))
        transactions.append(txn(checking_id, 50.00, 60, "PLANET FITNESS", "Gym Membership"))
        transactions.append(txn(chase_cc_id, 35.00, 28, "GREAT CLIPS", "Haircuts"))

        # ===== ENTERTAINMENT =====
        transactions.append(txn(checking_id, 15.99, 5, "NETFLIX", "Streaming Services"))
        transactions.append(txn(checking_id, 10.99, 5, "SPOTIFY", "Streaming Services"))
        transactions.append(txn(chase_cc_id, 14.99, 5, "DISNEY PLUS", "Streaming Services"))
        transactions.append(txn(amex_id, 65.00, 14, "AMC THEATRES", "Movies & Events"))
        transactions.append(txn(chase_cc_id, 49.99, 21, "STEAM GAMES", "Games"))
        transactions.append(txn(amex_id, 32.50, 35, "BARNES AND NOBLE", "Books"))

        # ===== SAVINGS & DEBT =====
        for month_offset in range(3):
            base_days = month_offset * 30
            transactions.append(txn(checking_id, 500.00, base_days + 1, "TRANSFER TO SAVINGS", "Emergency Fund"))
            transactions.append(txn(checking_id, 200.00, base_days + 1, "ROTH IRA CONTRIBUTION", "Retirement"))

        # Credit card payments
        transactions.append(txn(checking_id, 800.00, 15, "CHASE CARD PAYMENT", "Credit Card Payment"))
        transactions.append(txn(checking_id, 400.00, 45, "CHASE CARD PAYMENT", "Credit Card Payment"))

        # ===== TRANSFERS =====
        if savings_id:
            transactions.append(txn(checking_id, 1000.00, 7, "TRANSFER TO SAVINGS", "Transfer to Savings"))
            transactions.append(txn(savings_id, -1000.00, 7, "TRANSFER FROM CHECKING", "Transfer to Savings"))

        # ===== UNCATEGORIZED TRANSACTIONS =====
        transactions.append(txn(checking_id, 42.50, 3, "UNKNOWN VENDOR #12345", None))
        transactions.append(txn(chase_cc_id, 18.99, 8, "MISC PURCHASE", None))
        transactions.append(txn(checking_id, 75.00, 19, "CHECK #1042", None))
        transactions.append(txn(amex_id, 156.78, 27, "AMAZON MARKETPLACE", None))

        # ===== PENDING TRANSACTIONS =====
        transactions.append(txn(checking_id, 89.99, 0, "PENDING - BEST BUY", "Hobbies", pending=True))
        transactions.append(txn(chase_cc_id, 34.50, 0, "PENDING - UBER EATS", "Restaurants", pending=True))
        transactions.append(txn(checking_id, 250.00, 1, "PENDING - DOCTOR VISIT", "Doctor Visits", pending=True))

        # Create all transactions
        created = 0
        for t in transactions:
            if t["account_id"]:  # Only if we have a valid account
                result = self._post("/transactions/", t)
                if result:
                    self.transactions.append(result["transaction_id"])
                    created += 1

        log_success(f"Created {created} transactions")
        log_info(f"  - Categorized: {sum(1 for t in transactions if t.get('category_id'))}")
        log_info(f"  - Uncategorized: {sum(1 for t in transactions if not t.get('category_id'))}")
        log_info(f"  - Pending: {sum(1 for t in transactions if t.get('pending'))}")

    def seed_budgets(self):
        """Create budget entries for current and past months."""
        log_section("Seeding Budgets")

        today = date.today()

        # Budget amounts by category (monthly)
        budget_amounts = {
            # Income
            "Salary": 10000.00,
            "Freelance": 500.00,
            "Interest & Dividends": 15.00,

            # Housing
            "Rent/Mortgage": 1850.00,
            "Home Insurance": 100.00,
            "Home Maintenance": 100.00,

            # Food & Dining
            "Groceries": 600.00,
            "Restaurants": 200.00,
            "Coffee Shops": 50.00,
            "Fast Food": 50.00,

            # Transportation
            "Gas": 200.00,
            "Car Payment": 425.00,
            "Car Insurance": 120.00,
            "Car Maintenance": 50.00,
            "Public Transit": 0.00,
            "Parking": 20.00,

            # Utilities
            "Electricity": 120.00,
            "Water": 40.00,
            "Internet": 80.00,
            "Phone": 85.00,
            "Gas (Utility)": 30.00,

            # Healthcare
            "Health Insurance": 350.00,
            "Doctor Visits": 50.00,
            "Pharmacy": 30.00,
            "Dental": 25.00,

            # Personal
            "Clothing": 100.00,
            "Haircuts": 40.00,
            "Gym Membership": 50.00,
            "Personal Care": 30.00,

            # Entertainment
            "Streaming Services": 50.00,
            "Movies & Events": 50.00,
            "Hobbies": 100.00,
            "Games": 25.00,
            "Books": 25.00,

            # Savings & Debt
            "Emergency Fund": 500.00,
            "Retirement": 200.00,
            "Credit Card Payment": 500.00,
            "Student Loans": 0.00,
        }

        # Create budgets for current month and 2 previous months
        created = 0
        for month_offset in range(3):
            # Calculate first day of month
            month_date = today.replace(day=1) - timedelta(days=month_offset * 28)
            month_date = month_date.replace(day=1)
            month_str = month_date.strftime("%Y-%m")

            log_info(f"Creating budgets for {month_str}")

            for category_name, amount in budget_amounts.items():
                category_id = self.categories.get(category_name)
                if not category_id:
                    continue

                # Add some variance for past months
                variance = 1.0
                if month_offset > 0:
                    variance = random.uniform(0.9, 1.1)

                payload = {
                    "budget_month": str(month_date),
                    "planned_amount": round(amount * variance, 2),
                    "category_id": category_id,
                }

                result = self._post("/budget/", payload)
                if result:
                    self.budgets.append(result["budget_id"])
                    created += 1

        log_success(f"Created {created} budget entries")

    def print_summary(self):
        """Print a summary of all seeded data."""
        log_section("Seed Summary")

        print(f"Category Groups:  {len(self.groups)}")
        print(f"Categories:       {len(self.categories)}")
        print(f"Accounts:         {len(self.accounts)}")
        print(f"Transactions:     {len(self.transactions)}")
        print(f"Budget Entries:   {len(self.budgets)}")

        print(f"\n{Colors.GREEN}Seed completed successfully!{Colors.RESET}")
        print(f"\nYou can now test the application at:")
        print(f"  Frontend: http://localhost:12345")
        print(f"  Backend:  {self.base_url}")

    def run(self):
        """Run all seed operations."""
        log_section("Budget App - Comprehensive Seed Script")
        log_info(f"Target API: {self.base_url}")
        if self.clean:
            log_info("Clean mode enabled - will delete existing data first")

        # Test connection
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            log_success("API connection successful")
        except requests.RequestException:
            log_info("Health endpoint not available, continuing anyway...")

        self.clear_existing_data()
        self.seed_category_groups()
        self.seed_categories()
        self.seed_accounts()
        self.seed_transactions()
        self.seed_budgets()
        self.print_summary()


def main():
    parser = argparse.ArgumentParser(description="Seed the Budget App database with test data")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing transactions, budgets, and accounts before seeding",
    )
    args = parser.parse_args()

    seeder = BudgetSeeder(args.base_url, clean=args.clean)
    seeder.run()


if __name__ == "__main__":
    main()
