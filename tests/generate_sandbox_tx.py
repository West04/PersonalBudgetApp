import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

# Add project root to path so we can import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import SessionLocal
from backend.models import PlaidItem
from backend.security import decrypt_token

load_dotenv()

def generate_transactions():
    PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
    PLAID_SECRET = os.getenv("PLAID_SECRET")
    PLAID_ENVIRONMENT = os.getenv("PLAID_ENVIRONMENT", "Sandbox")

    if PLAID_ENVIRONMENT != "Sandbox":
        print("Error: This script only works in Sandbox mode.")
        return

    db = SessionLocal()
    try:
        # Get the first PlaidItem in the database
        item = db.query(PlaidItem).first()
        if not item:
            print("Error: No Plaid items found in database. Connect an account first.")
            return

        access_token = decrypt_token(item.plaid_access_token_encrypted)
        if not access_token:
            print("Error: Could not decrypt access token.")
            return

        print(f"Triggering transaction generation for Item ID: {item.plaid_item_id}")

        PLAID_BASE = "https://sandbox.plaid.com"
        headers = {
            "Content-Type": "application/json",
            "PLAID-CLIENT-ID": PLAID_CLIENT_ID,
            "PLAID-SECRET": PLAID_SECRET,
        }

        # Generate a few dummy transactions
        today = date.today()
        transactions = []
        for i in range(5):
            tx_date = (today - timedelta(days=i)).isoformat()
            transactions.append({
                "amount": 10.0 * (i + 1),
                "description": f"Test Transaction {i+1}",
                "date_posted": tx_date,
                "date_transacted": tx_date,
            })

        body = {
            "access_token": access_token,
            "transactions": transactions,
        }

        resp = requests.post(f"{PLAID_BASE}/sandbox/transactions/create", json=body, headers=headers, timeout=60)
        
        if resp.status_code == 200:
            print("Successfully triggered transaction generation!")
            print("Note: It may take a few seconds for Plaid to process them.")
            print("Run your sync endpoint afterwards to pull them into the database.")
        else:
            print(f"Failed to generate transactions: {resp.status_code}")
            print(resp.text)

    finally:
        db.close()

if __name__ == "__main__":
    generate_transactions()
